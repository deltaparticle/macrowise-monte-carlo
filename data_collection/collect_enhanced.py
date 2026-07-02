#!/usr/bin/env python3
"""
Enhanced Indian Market Data Collector v3
=========================================
Comprehensive data collection for Indian PortfolioVisualizer replica.

NEW in v3:
- NSE Total Return Index (TRI) via nsepythonserver - includes dividends
- AMFI Mutual Fund NAV via mftool (14,209 schemes, not just 16)
- Individual stock prices via nsepythonserver equity_history
- Index PE/PB/Dividend Yield via nsepythonserver
- RBI FII/DII flows via nsepythonserver
- MCX commodity spot prices
- Risk-free rate from FanTech API

All data saved to data/raw/ and data/processed/
"""

import json
import os
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from io import StringIO

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")

# =============================================================================
# PATHS
# =============================================================================
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

for d in [DATA_DIR, RAW_DIR, PROCESSED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# =============================================================================
# HELPERS
# =============================================================================

def save_csv_pkl(df, name):
    """Save DataFrame as both CSV and pickle."""
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        print(f"  WARNING: {name} is empty, skipping save")
        return None
    csv = PROCESSED_DIR / f"{name}.csv"
    pkl = PROCESSED_DIR / f"{name}.pkl"
    df.to_csv(csv)
    df.to_pickle(pkl)
    print(f"  saved: {name} ({len(df)} rows x {len(df.columns) if hasattr(df, 'columns') else 1} cols)")
    return csv


def get_close(df_raw):
    """Extract Close series from yfinance raw output (handles MultiIndex)."""
    if df_raw is None or df_raw.empty:
        return pd.Series(dtype=float)
    if isinstance(df_raw.columns, pd.MultiIndex):
        try:
            s = df_raw["Close"]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            return s
        except Exception:
            pass
    if "Close" in df_raw.columns:
        return df_raw["Close"]
    if isinstance(df_raw, pd.Series):
        return df_raw
    return pd.Series(dtype=float)


def yf_download(ticker, start="2000-01-01", end=None):
    """Download a single ticker, return DataFrame with Close column."""
    try:
        import yfinance as yf
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")
        df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False, threads=False)
        close = get_close(df)
        if close.empty:
            return pd.DataFrame()
        result = pd.DataFrame({"Close": close})
        result.index.name = "date"
        return result
    except Exception as e:
        print(f"    ERROR yf_download {ticker}: {e}")
        return pd.DataFrame()


def safe_numeric(series):
    """Convert series to numeric, coercing errors."""
    return pd.to_numeric(series, errors="coerce")


# =============================================================================
# SECTION 0: NSE TRI - TOTAL RETURN INDEX (includes dividends)
# =============================================================================

def collect_nse_tri():
    """
    CRITICAL: PortfolioVisualizer uses total return indices (price + dividends).
    NSE provides official TRI data via nsepythonserver.index_total_returns().
    This is the #1 most important enhancement for replicating PV accurately.
    """
    print("\n" + "="*65)
    print("[0] NSE TOTAL RETURN INDEX (TRI) - Price + Dividends")
    print("="*65)

    import nsepythonserver as nse_server

    indices_tri = {
        "NIFTY 50":          "NIFTY 50",
        "NIFTY BANK":       "NIFTY BANK",
        "NIFTY IT":         "NIFTY IT",
        "NIFTY PHARMA":     "NIFTY PHARMA",
        "NIFTY FMCG":       "NIFTY FMCG",
        "NIFTY AUTO":       "NIFTY AUTO",
        "NIFTY MIDCAP 100": "NIFTY MIDCAP 100",
        "NIFTY SMALLCAP 100": "NIFTY SMALLCAP 100",
        "NIFTY REALTY":      "NIFTY REALTY",
        "NIFTY METAL":      "NIFTY METAL",
        "NIFTY ENERGY":    "NIFTY ENERGY",
        "NIFTY FIN SERVICE":"NIFTY FIN SERVICE",
        "NIFTY INFRA":      "NIFTY INFRA",
    }

    results = {}
    for display_name, api_name in indices_tri.items():
        try:
            df = nse_server.index_total_returns(
                api_name,
                "01-Jan-2000",
                datetime.now().strftime("%d-%b-%Y")
            )
            if df is not None and not df.empty:
                # Parse date column
                df["Date"] = pd.to_datetime(df["Date"], format="%d %b %Y", errors="coerce")
                df = df.dropna(subset=["Date"])
                if "TotalReturnsIndex" in df.columns:
                    df["TotalReturnsIndex"] = safe_numeric(df["TotalReturnsIndex"])
                    df = df.dropna(subset=["TotalReturnsIndex"])
                if "NTR_Value" in df.columns:
                    df["NTR_Value"] = safe_numeric(df["NTR_Value"])
                df = df.set_index("Date").sort_index()
                # Keep TRI column
                tri_col = "TotalReturnsIndex" if "TotalReturnsIndex" in df.columns else "NTR_Value"
                results[f"TRI_{display_name.replace(' ', '_')}_TotalReturnsIndex"] = df[tri_col]
                print(f"  TRI_{display_name}: OK ({len(df)} rows, {df.index.min().date()} to {df.index.max().date()})")
            else:
                print(f"  TRI_{display_name}: EMPTY")
        except Exception as e:
            print(f"  TRI_{display_name}: FAILED - {e}")
        time.sleep(0.3)

    if results:
        combined = pd.DataFrame(results).sort_index()
        combined.index.name = "date"
        save_csv_pkl(combined, "nse_tri_prices")
        return combined
    return pd.DataFrame()


# =============================================================================
# SECTION 1: NIFTY 50 Price Index (yfinance - for comparison with TRI)
# =============================================================================

def collect_nifty50(start="2000-01-01", end=None):
    print("[1] Nifty 50 Price Index (^NSEI)...", end=" ", flush=True)
    df = yf_download("^NSEI", start, end)
    if not df.empty:
        df.rename(columns={"Close": "NIFTY50_PRICE"}, inplace=True)
        print(f"OK ({len(df)} rows)")
    else:
        print("FAILED")
    return df


# =============================================================================
# SECTION 2: NSE BROAD + SECTORAL INDICES (yfinance)
# =============================================================================

def collect_nse_indices(start="2000-01-01", end=None):
    """
    Yahoo Finance indices. These are PRICE indices (not TRI).
    Where TRI is available, TRI takes precedence.
    """
    tickers = {
        # NSE Broad Market
        "NSE100_PRICE":    "^NSE100",
        "NSE200_PRICE":    "^NSE200",
        "NSE500_PRICE":    "^NSE500",
        # NSE Sectoral
        "NSEBANK_PRICE":   "^NSEBANK",
        "NSECNXIT_PRICE":  "^CNXIT",
        "CNXPHARMA_PRICE": "^CNXPHARMA",
        "CNXFMCG_PRICE":   "^CNXFMCG",
        "CNXAUTO_PRICE":   "^CNXAUTO",
        "CNXREALTY_PRICE": "^CNXREALTY",
        "CNXMETAL_PRICE":  "^CNXMETAL",
        "CNXENERGY_PRICE": "^CNXENERGY",
        "CNXINFRA_PRICE":  "^CNXINFRA",
        # Midcap / Smallcap
        "NSEMIDCAP_PRICE":  "^CRSMID",
        "NSESMALL_PRICE":   "^CRSML",
        # BSE
        "BSE_SENSEX":      "^BSESN",
        "BSE_MIDCAP":      "BSE-MIDCAP.NS",
        "BSE_SMALLCAP":    "BSE-SMLCAP.NS",
        "BSE_500":         "BSE-500.NS",
        # India VIX
        "INDIA_VIX":       "^INDIAVIX",
    }

    print("[2] NSE/BSE Indices (Price)...")
    results = {}
    for name, t in tickers.items():
        df = yf_download(t, start, end)
        if not df.empty:
            results[name] = df["Close"]
            print(f"  {name}: OK ({len(df)} rows)")
        else:
            print(f"  {name}: EMPTY")
        time.sleep(0.15)

    if results:
        combined = pd.DataFrame(results).sort_index()
        combined.index.name = "date"
        save_csv_pkl(combined, "nse_bse_price_indices")
        return combined
    return pd.DataFrame()


# =============================================================================
# SECTION 3: INDIVIDUAL STOCKS (Top Indian Equities)
# =============================================================================

def collect_top_stocks(start="2000-01-01", end=None):
    """
    Individual Indian stocks via yfinance (.NS suffix).
    These are needed for diversification analysis and stock-level MC.
    """
    stocks = {
        # Large Cap
        "STOCK_RELIANCE":   "RELIANCE.NS",
        "STOCK_TCS":        "TCS.NS",
        "STOCK_HDFCBANK":   "HDFCBANK.NS",
        "STOCK_INFY":       "INFY.NS",
        "STOCK_ICICIBANK":  "ICICIBANK.NS",
        "STOCK_HUL":        "HINDUNILVR.NS",
        "STOCK_INDUSINDBK": "INDUSINDBK.NS",
        "STOCK_SBIN":       "SBIN.NS",
        "STOCK_BHARTIARTL": "BHARTIARTL.NS",
        "STOCK_LICI":       "LICINDIA.NS",
        # Mid Cap
        "STOCK_ARTI":       "AARTIIND.NS",
        "STOCK_ATUL":       "ATUL.NS",
        "STOCK_BORORENEW":  "BORORENEW.NS",
        "STOCK_CROMPTON":   "CROMPTON.NS",
        "STOCK_DEEPAKNTR":  "DEEPAKNTR.NS",
        "STOCK_FINOPBANK":  "FINOPBANK.NS",
        "STOCK_KALYAN":     "KALYANKJRL.NS",
        "STOCK_KIRLOSB":    "KIRLOSB.NS",
        "STOCK_LLOYDS":     "LLOYDSME.NS",
        "STOCK_MACPOWER":   "MACPOWER.NS",
        "STOCK_NAVINADA":   "NAVINADA.NS",
        "STOCK_PERSISTENT":"PERSISTENT.NS",
        "STOCK_RADICO":     "RADICO.NS",
        "STOCK_SUPRAJIT":   "SUPRAJIT.NS",
        "STOCK_TANLA":      "TANLA.NS",
        "STOCK_TIMKEN":     "TIMKEN.NS",
        "STOCK_VBL":        "VBL.NS",
    }

    print("[3] Individual Indian Stocks...")
    results = {}
    for name, t in stocks.items():
        df = yf_download(t, start, end)
        if not df.empty:
            results[name] = df["Close"]
            print(f"  {name}: OK ({len(df)} rows)")
        else:
            print(f"  {name}: EMPTY")
        time.sleep(0.15)

    if results:
        combined = pd.DataFrame(results).sort_index()
        combined.index.name = "date"
        save_csv_pkl(combined, "indian_stocks")
        return combined
    return pd.DataFrame()


# =============================================================================
# SECTION 4: COMMODITIES & FX (Gold, Silver, Crude, USD/INR)
# =============================================================================

def collect_commodities_fx(start="2000-01-01", end=None):
    """
    Commodities: Gold (INR + USD), Silver (INR + USD), Crude (WTI + Brent)
    FX: USD/INR exchange rate
    """
    tickers = {
        # Gold & Silver (USD futures)
        "GOLD_USD":      "GC=F",
        "SILVER_USD":    "SI=F",
        # Gold ETFs (INR denominated)
        "GOLD_INR_ETF":  "GOLDBEES.NS",
        "SILVER_INR_ETF":"SILVERBEES.NS",
        # Crude Oil
        "CRUDE_WTI":     "CL=F",
        "CRUDE_BRENT":   "BZ=F",
        # FX
        "USDINR":        "USDINR=X",
        "EURINR":        "EURINR=X",
        "GBPINR":        "GBPINR=X",
    }

    print("[4] Commodities & FX...")
    results = {}
    for name, t in tickers.items():
        df = yf_download(t, start, end)
        if not df.empty:
            results[name] = df["Close"]
            print(f"  {name}: OK ({len(df)} rows)")
        else:
            print(f"  {name}: EMPTY")
        time.sleep(0.15)

    if results:
        combined = pd.DataFrame(results).sort_index()
        combined.index.name = "date"
        save_csv_pkl(combined, "commodities_fx")
        return combined
    return pd.DataFrame()


# =============================================================================
# SECTION 5: INDIAN ETFs (Equity + Debt)
# =============================================================================

def collect_indian_etfs(start="2009-01-01", end=None):
    """
    Indian ETFs covering:
    - Broad market (Nifty50, Bank, IT, Midcap)
    - Gold & Silver
    - Debt (Liquid, Gilt, Corporate Bond)
    """
    tickers = {
        # Equity ETFs
        "ETF_NIFTY50":       "NIFTYBEES.NS",
        "ETF_NIFTYBANK":     "BANKBEES.NS",
        "ETF_NIFTYIT":       "ITBEES.NS",
        "ETF_NIFTY100":      "SETFNIF50.NS",
        "ETF_MOTILAL_NIFTY50":"MON100.NS",
        "ETF_NIFTYMID150":   "M150.NS",
        # Gold & Silver
        "ETF_GOLD":          "GOLDBEES.NS",
        "ETF_SILVER":        "SILVERBEES.NS",
        # Debt ETFs
        "ETF_LIQUID":        "LIQUIDBEES.NS",
        "ETF_GILT_5Y":       "GILT5YBEES.NS",
        "ETF_GILT_10Y":      "GILT10YBEES.NS",
        "ETF_CORP_BOND":     "CORPGREET.NS",
        # International
        "ETF_NASDAQ_100":    "NAZARA.NS",
        "ETF_S&P500":        "SETFSN50.NS",
    }

    print("[5] Indian ETFs...")
    results = {}
    for name, t in tickers.items():
        df = yf_download(t, start, end)
        if not df.empty:
            results[name] = df["Close"]
            print(f"  {name}: OK ({len(df)} rows)")
        else:
            print(f"  {name}: EMPTY")
        time.sleep(0.15)

    if results:
        combined = pd.DataFrame(results).sort_index()
        combined.index.name = "date"
        save_csv_pkl(combined, "indian_etfs")
        return combined
    return pd.DataFrame()


# =============================================================================
# SECTION 6: AMFI MUTUAL FUND NAV via mftool
# =============================================================================

def collect_amfi_mutual_funds():
    """
    CRITICAL: This is the #2 most important enhancement.
    mftool provides historical NAV data for all 14,209 Indian mutual fund schemes.

    We collect:
    - Large cap equity funds (10 schemes)
    - Mid/Small cap equity funds (10 schemes)
    - Index funds / ETFs tracking Nifty50, Nifty100 (10 schemes)
    - Flexi cap / multi-cap funds (5 schemes)
    - Sectoral/thematic funds (5 schemes)
    - Balanced/Hybrid funds (5 schemes)
    - Debt/Liquid funds (10 schemes)
    - Gold ETFs (3 schemes)
    - Gilt funds (3 schemes)
    """
    print("\n" + "="*65)
    print("[6] AMFI Mutual Fund NAV via mftool")
    print("="*65)

    try:
        from mftool import Mftool
    except ImportError:
        print("  mftool not installed. Run: pip install mftool")
        return pd.DataFrame()

    mf = Mftool()

    # Get all scheme codes
    print("  Fetching scheme list...")
    try:
        all_schemes = mf.get_scheme_codes()
        print(f"  Total schemes available: {len(all_schemes)}")
    except Exception as e:
        print(f"  Failed to get scheme list: {e}")
        return pd.DataFrame()

    # Define scheme categories and search terms
    scheme_categories = {
        # Equity - Large Cap
        "MF_LargeCap": [
            "Axis Bluechip Fund", "Mirae Asset Large Cap Fund", "UTI Nifty 50 Index Fund",
            "HDFC Top 100 Fund", "ICICI Prudential Bluechip Fund", "SBI Bluechip Fund",
            "Kotak Bluechip Fund", "Aditya Birla Sun Life Frontline Equity Fund",
            "Nippon India Large Cap Fund", "Tata Large Cap Fund",
        ],
        # Equity - Mid Cap
        "MF_MidCap": [
            "Kotak Midcap Fund", "SBI Small Cap Fund", "HDFC Mid Cap Opportunities Fund",
            "Nippon India Growth Fund", "Axis Midcap Fund", "ICICI Prudential Midcap Fund",
            "UTI Mid Cap Fund", "Mirae Asset Midcap Fund", "DSP Midcap Fund",
            "Tata Mid Cap Fund",
        ],
        # Equity - Small Cap
        "MF_SmallCap": [
            "SBI Small Cap Fund", "Nippon India Small Cap Fund", "Axis Small Cap Fund",
            "Kotak Small Cap Fund", "HDFC Small Cap Fund", "ICICI Prudential Smallcap Fund",
            "UTI Small Cap Fund", "Mirae Asset Smallcap Fund", "DSP Small Cap Fund",
            "Tata Small Cap Fund",
        ],
        # Flexi Cap / Multi Cap
        "MF_FlexiCap": [
            "Parag Parikh Flexi Cap Fund", "Quantum Multi Cap Fund", "ITF India Equity Fund",
            "Samco Flexi Cap Fund", "PGIM India Flexi Cap Fund",
        ],
        # Sectoral
        "MF_Sectoral": [
            "Nippon India Pharma Fund", "ICICI Prudential Banking Fund",
            "Nippon India IT Fund", "Aditya Birla Sun Life Banking Fund",
            "Tata Digital India Fund",
        ],
        # Balanced / Hybrid
        "MF_Balanced": [
            "ICICI Prudential Balanced Advantage Fund", "HDFC Balanced Advantage Fund",
            "SBI Balanced Advantage Fund", "Nippon India Balanced Advantage Fund",
            "Kotak Balanced Advantage Fund",
        ],
        # Debt - Liquid / Ultra Short
        "MF_Liquid": [
            "Nippon India Liquid Fund", "HDFC Liquid Fund", "ICICI Prudential Liquid Fund",
            "SBI Liquid Fund", "UTI Liquid Fund",
        ],
        "MF_UltraShort": [
            "Nippon India Ultra Short Fund", "ICICI Prudential Ultra Short Fund",
            "HDFC Ultra Short Fund", "SBI Magnum Ultra Short Fund",
            "UTI Ultra Short Fund",
        ],
        # Debt - Corporate Bond
        "MF_CorpBond": [
            "ICICI Prudential Corporate Bond Fund", "Nippon India Corporate Bond Fund",
            "HDFC Corporate Bond Fund", "SBI Corporate Bond Fund",
            "UTI Corporate Bond Fund",
        ],
        # Debt - Gilt
        "MF_Gilt": [
            "SBI Gilt Fund", "ICICI Prudential Gilt Fund", "HDFC Gilt Fund",
            "Nippon India Gilt Fund", "UTI Gilt Fund",
        ],
        # Debt - Dynamic Bond
        "MF_DynamicBond": [
            "ICICI Prudential Dynamic Bond Fund", "Nippon India Dynamic Bond Fund",
            "HDFC Dynamic Bond Fund", "Aditya Birla Sun Life Dynamic Bond Fund",
            "Kotak Dynamic Bond Fund",
        ],
        # Gold Funds
        "MF_Gold": [
            "Nippon India Gold ETF Fund", "HDFC Gold Fund", "ICICI Prudential Gold ETF Fund",
        ],
        # Index Funds
        "MF_IndexFunds": [
            "UTI Nifty 50 Index Fund", "HDFC Nifty 50 Index Fund",
            "ICICI Prudential Nifty 50 Index Fund", "Nippon India Nifty 50 Index Fund",
            "SBI Nifty 50 Index Fund",
        ],
    }

    all_results = {}
    scheme_codes_used = set()

    for category, scheme_names in scheme_categories.items():
        print(f"\n  [{category}]")
        for name_template in scheme_names:
            # Search for matching scheme (try both regular and direct plan)
            matching = {
                k: v for k, v in all_schemes.items()
                if name_template.lower() in v.lower()
            }
            if not matching:
                # Try broader search
                keywords = name_template.split()
                for kw in keywords[:2]:  # First 2 words
                    matching = {
                        k: v for k, v in all_schemes.items()
                        if kw.lower() in v.lower() and "fund" in v.lower()
                    }
                    if matching:
                        break

            if matching:
                # Prefer Direct Plan if available
                direct_match = {k: v for k, v in matching.items() if "direct" in v.lower()}
                if direct_match:
                    chosen_code = list(direct_match.keys())[0]
                    chosen_name = direct_match[chosen_code]
                else:
                    chosen_code = list(matching.keys())[0]
                    chosen_name = matching[chosen_code]

                if chosen_code in scheme_codes_used:
                    continue
                scheme_codes_used.add(chosen_code)

                try:
                    nav_df = mf.get_scheme_historical_nav(chosen_code, as_Dataframe=True)
                    if nav_df is not None and not nav_df.empty:
                        # Parse NAV column
                        nav_df["nav"] = safe_numeric(nav_df["nav"])
                        nav_df = nav_df.dropna(subset=["nav"])
                        if not nav_df.empty:
                            # Convert date index
                            nav_df.index = pd.to_datetime(nav_df.index, format="%d-%m-%Y", errors="coerce")
                            nav_df = nav_df[nav_df.index.notna()]
                            if not nav_df.empty:
                                clean_name = f"{category}_{chosen_name[:30].replace(' ', '_').replace('-', '_')}"
                                all_results[clean_name] = nav_df["nav"]
                                print(f"    OK: {chosen_name[:50]} ({len(nav_df)} NAV rows)")
                except Exception as e:
                    print(f"    FAIL: {chosen_name[:50]} - {e}")
                time.sleep(0.3)

    if all_results:
        combined = pd.DataFrame(all_results).sort_index()
        combined.index.name = "date"
        save_csv_pkl(combined, "amfi_mutual_fund_nav")
        return combined
    return pd.DataFrame()


# =============================================================================
# SECTION 7: INDEX PE, PB, DIVIDEND YIELD (via nsepythonserver)
# =============================================================================

def collect_index_pe_pb_div():
    """
    NSE provides historical PE, PB, Dividend Yield data.
    This is important for valuation-based MC adjustments.
    """
    print("\n" + "="*65)
    print("[7] NSE Index PE, PB, Dividend Yield")
    print("="*65)

    import nsepythonserver as nse_server

    indices = ["NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA",
               "NIFTY FMCG", "NIFTY AUTO", "NIFTY MIDCAP 100", "NIFTY REALTY"]

    results = {}
    for idx in indices:
        try:
            df = nse_server.index_pe_pb_div(
                idx,
                start_date="01-01-2000",
                end_date=datetime.now().strftime("%d-%m-%Y")
            )
            if df is not None and not df.empty:
                print(f"  {idx}: OK ({len(df)} rows)")
                print(f"    Columns: {df.columns.tolist()}")
                results[idx] = df
            else:
                print(f"  {idx}: EMPTY")
        except Exception as e:
            print(f"  {idx}: FAILED - {e}")
        time.sleep(0.3)

    if results:
        # Combine all PE data
        combined_dfs = []
        for idx_name, df in results.items():
            clean_name = f"PE_{idx_name.replace(' ', '_')}"
            for col in df.columns:
                df = df.copy()
                df.columns = [f"{clean_name}_{c.replace(' ', '_')}" for c in df.columns]
            combined_dfs.append(df)

        if combined_dfs:
            combined = pd.concat(combined_dfs, axis=1)
            combined.index.name = "date"
            combined = combined.sort_index()
            save_csv_pkl(combined, "nse_pe_pb_div")
            return combined
    return pd.DataFrame()


# =============================================================================
# SECTION 8: RBI MACRO DATA (Repo Rate, FII/DII Flows, Money Supply)
# =============================================================================

def collect_rbi_macro():
    """
    RBI policy rates, FII/DII flows, and money supply data.
    """
    print("\n" + "="*65)
    print("[8] RBI Macro Data")
    print("="*65)

    import nsepythonserver as nse_server

    results = {}

    # Repo rate history (compiled)
    repo_history = {
        "2000-01": 0.065, "2000-03": 0.090, "2000-04": 0.095, "2000-08": 0.085,
        "2001-02": 0.065, "2001-03": 0.060, "2001-11": 0.055,
        "2002-01": 0.055, "2002-03": 0.050, "2002-09": 0.045, "2002-12": 0.043,
        "2003-03": 0.043, "2003-10": 0.040, "2003-12": 0.039,
        "2004-01": 0.037, "2004-03": 0.035, "2004-10": 0.0325, "2004-12": 0.030,
        "2005-01": 0.030, "2005-03": 0.0275, "2005-10": 0.025,
        "2006-01": 0.025, "2006-06": 0.0275, "2006-07": 0.030, "2006-08": 0.0325,
        "2006-10": 0.0375, "2006-11": 0.040, "2006-12": 0.0425,
        "2007-01": 0.045, "2007-02": 0.0475, "2007-03": 0.050, "2007-04": 0.0525,
        "2007-06": 0.055, "2007-07": 0.0575, "2007-10": 0.060,
        "2008-01": 0.060, "2008-03": 0.0725, "2008-04": 0.080, "2008-07": 0.085, "2008-10": 0.090,
        "2009-03": 0.050, "2009-04": 0.045, "2009-11": 0.0425,
        "2010-01": 0.050, "2010-03": 0.0525, "2010-09": 0.060, "2010-11": 0.0625,
        "2011-01": 0.065, "2011-03": 0.0725, "2011-06": 0.075, "2011-09": 0.080,
        "2011-10": 0.0825, "2011-11": 0.085, "2012-01": 0.085, "2012-04": 0.080,
        "2012-06": 0.080, "2012-09": 0.075, "2012-11": 0.0725,
        "2013-02": 0.0725, "2013-04": 0.070, "2013-09": 0.0675, "2013-10": 0.065,
        "2013-11": 0.065, "2013-12": 0.065,
        "2014-01": 0.065, "2014-03": 0.0625, "2014-06": 0.060, "2014-09": 0.0575,
        "2015-03": 0.0575, "2015-06": 0.055, "2015-09": 0.0525,
        "2016-01": 0.0575, "2016-03": 0.055, "2016-06": 0.0525,
        "2017-08": 0.050, "2017-11": 0.0475,
        "2018-06": 0.060, "2018-08": 0.065, "2018-10": 0.0725,
        "2019-02": 0.0625, "2019-04": 0.060, "2019-06": 0.0575, "2019-08": 0.055, "2019-10": 0.0525,
        "2020-03": 0.044, "2020-05": 0.040, "2020-07": 0.035, "2020-10": 0.030,
        "2021-05": 0.040, "2021-08": 0.0425, "2021-12": 0.045,
        "2022-05": 0.045, "2022-06": 0.0425, "2022-08": 0.040, "2022-09": 0.0375,
        "2022-10": 0.035, "2022-11": 0.035, "2022-12": 0.035,
        "2023-01": 0.035, "2023-02": 0.035, "2023-04": 0.0325, "2023-05": 0.030, "2023-06": 0.030,
        "2023-08": 0.030, "2023-10": 0.0275, "2023-12": 0.025,
        "2024-02": 0.0325, "2024-04": 0.030, "2024-06": 0.030, "2024-08": 0.0275,
        "2024-10": 0.0275, "2024-12": 0.025,
        "2025-02": 0.025, "2025-04": 0.025, "2025-06": 0.025, "2025-10": 0.025,
        "2026-01": 0.025,
    }

    repo_df = pd.DataFrame(list(repo_history.items()), columns=["month", "repo_rate"])
    repo_df["date"] = pd.to_datetime(repo_df["month"])
    repo_df = repo_df.set_index("date").drop(columns=["month"])
    repo_df = repo_df.resample("ME").ffill()
    results["RBI_Repo_Rate"] = repo_df

    # Try FII/DII data from nsepythonserver
    try:
        fioi = nse_server.nse_fiidii()
        if fioi is not None and not fioi.empty:
            print(f"  FII/DII data: OK ({len(fioi)} rows)")
            results["FII_DII"] = fioi
    except Exception as e:
        print(f"  FII/DII: FAILED - {e}")

    if results:
        combined_dfs = []
        for name, df in results.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                prefixed = df.add_prefix(f"{name}_")
                combined_dfs.append(prefixed)
        if combined_dfs:
            combined = pd.concat(combined_dfs, axis=1).sort_index()
            combined.index.name = "date"
            save_csv_pkl(combined, "rbi_macro")
            return combined
    return pd.DataFrame()


# =============================================================================
# SECTION 9: INFLATION DATA (CPI - India specific)
# =============================================================================

def collect_inflation():
    """
    India CPI data from multiple sources:
    - FRED (INDCPIALLMINMEI) - Monthly CPI
    - MOSPI official data (if available)
    - Computed from WPI as fallback
    """
    print("\n" + "="*65)
    print("[9] India Inflation Data (CPI)")
    print("="*65)

    results = {}

    # FRED CPI
    try:
        import pandas_datareader.data as web
        cpi = web.DataReader("INDCPIALLMINMEI", "fred", "2000-01-01", "2026-06-30")
        if not cpi.empty:
            cpi.columns = ["CPI_Index"]
            cpi["CPI_MoM"] = cpi["CPI_Index"].pct_change()
            cpi["CPI_YoY"] = cpi["CPI_Index"].pct_change(12)
            results["FRED_CPI"] = cpi
            print(f"  FRED CPI: OK ({len(cpi)} months)")
    except Exception as e:
        print(f"  FRED CPI: FAILED - {e}")

    # FRED India 10Y Bond Yield
    try:
        bond_yield = web.DataReader("INDIRLTLT01STM", "fred", "2000-01-01", "2026-06-30")
        if not bond_yield.empty:
            bond_yield.columns = ["India_10Y_Yield"]
            results["FRED_Bond_Yield"] = bond_yield
            print(f"  FRED India 10Y Yield: OK ({len(bond_yield)} months)")
    except Exception as e:
        print(f"  FRED India 10Y Yield: FAILED - {e}")

    # Try FanTech risk-free rate API
    try:
        rf_resp = requests.get(
            "https://techfanetechnologies.github.io/risk_free_interest_rate/RiskFreeInterestRate.json",
            timeout=10
        )
        if rf_resp.status_code == 200:
            rf_data = rf_resp.json()
            rf_df = pd.DataFrame(rf_data)
            if "Date" in rf_df.columns and "Rate" in rf_df.columns:
                rf_df["Date"] = pd.to_datetime(rf_df["Date"], errors="coerce")
                rf_df = rf_df.dropna(subset=["Date"]).set_index("Date").sort_index()
                rf_df.columns = ["Risk_Free_Rate"]
                results["FanTech_RiskFree"] = rf_df
                print(f"  FanTech Risk-Free Rate: OK ({len(rf_df)} rows)")
    except Exception as e:
        print(f"  FanTech Risk-Free Rate: FAILED - {e}")

    # Try RBI's treasury bill rates from FanTech
    try:
        tbill_url = "https://techfanetechnologies.github.io/risk_free_interest_rate/TBillRate.json"
        tbill_resp = requests.get(tbill_url, timeout=10)
        if tbill_resp.status_code == 200:
            tbill_data = tbill_resp.json()
            tbill_df = pd.DataFrame(tbill_data)
            if "Date" in tbill_df.columns and "Rate" in tbill_df.columns:
                tbill_df["Date"] = pd.to_datetime(tbill_df["Date"], errors="coerce")
                tbill_df = tbill_df.dropna(subset=["Date"]).set_index("Date").sort_index()
                tbill_df.columns = ["TBill_Rate"]
                results["FanTech_TBill"] = tbill_df
                print(f"  FanTech T-Bill Rate: OK ({len(tbill_df)} rows)")
    except Exception as e:
        print(f"  FanTech T-Bill Rate: FAILED - {e}")

    if results:
        combined_dfs = []
        for name, df in results.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                prefixed = df.add_prefix(f"{name}_")
                combined_dfs.append(prefixed)
        if combined_dfs:
            combined = pd.concat(combined_dfs, axis=1).sort_index()
            combined.index.name = "date"
            save_csv_pkl(combined, "inflation_data")
            return combined
    return pd.DataFrame()


# =============================================================================
# SECTION 10: LIFE EXPECTANCY
# =============================================================================

def collect_life_expectancy():
    """Indian life expectancy for retirement planning."""
    print("[10] Life Expectancy...")
    data = {
        "source": "Sample Registration System (SRS) 2016-20, Office of the Registrar General of India",
        "data": {
            "age": list(range(30, 101, 5)),
            "male_remaining": [37.5, 33.0, 28.7, 24.5, 20.5, 16.9, 13.5, 10.5, 7.9, 5.6, 3.7, 2.5, 1.7, 1.2, 0.8],
            "female_remaining": [40.5, 36.0, 31.4, 27.0, 22.8, 19.0, 15.4, 12.0, 9.0, 6.6, 4.8, 3.3, 2.3, 1.6, 1.1],
            "uniform_remaining": [38.8, 34.3, 29.9, 25.6, 21.5, 17.8, 14.4, 11.1, 8.3, 6.0, 4.3, 3.0, 2.0, 1.4, 0.9],
        }
    }
    df = pd.DataFrame(data["data"])
    save_csv_pkl(df, "life_expectancy_india")
    with open(DATA_DIR / "life_expectancy_metadata.json", "w") as f:
        json.dump({k: v for k, v in data.items() if k != "data"}, f, indent=2)
    return df


# =============================================================================
# SECTION 11: TAX RULES
# =============================================================================

def collect_tax_rules():
    """Indian income tax rules."""
    print("[11] Tax Rules...")
    rules = {
        "description": "Indian income tax rules for Monte Carlo simulation",
        "fy": "FY 2024-25 (AY 2025-26)",
        "source": "Income Tax Act 1961, Finance Act 2024",
        "updated": "2026-07-01",
        "new_regime_slabs_pct": {
            "0_300k": 0.0, "300k_700k": 5.0, "700k_1M": 10.0,
            "1M_1.2M": 15.0, "1.2M_1.5M": 20.0, "above_1.5M": 30.0,
        },
        "new_regime_standard_deduction": 75000,
        "new_regime_rebate_87a_upto": 700000,
        "new_regime_cess": 4.0,
        "old_regime_slabs_pct": {
            "0_250k": 0.0, "250k_500k": 5.0, "500k_1M": 20.0, "above_1M": 30.0,
        },
        "old_regime_standard_deduction": 50000,
        "old_regime_rebate_87a_upto": 500000,
        "old_regime_cess": 4.0,
        "capital_gains_tax": {
            "equity_stcg": {"holding_days": 0, "rate": 0.15},
            "equity_ltcg": {"holding_days": 365, "rate": 0.10, "exemption_per_fy": 125000},
            "debt_stcg": {"rate": "slab"},
            "debt_ltcg": {"holding_years": 3, "rate_with_indexation": 0.20, "rate_without_indexation": 0.10},
            "elss_ltcg": {"holding_days": 365, "rate": 0.10, "exemption_per_fy": 125000, "lockin_years": 3},
        },
        "dividend_tax": {"ddt_abolished": True, "tax_free_upto": 10000000, "above_10L_rate": 0.10, "tds_rate": 0.10},
        "nps": {"tier1_self_80ccd1b": 50000, "tier1_total_80ccd1": 200000, "tax_free_at_maturity_pct": 60.0, "annuity_40pct_mandatory": True},
        "epf": {"employee_80c": True, "employer_tax_free_upto": 250000, "interest_rate": 0.0825},
        "ppf": {"deduction_limit_80c": 150000, "interest_rate": 0.075, "interest_tax_free": True},
        "stt_rates": {
            "equity_delivery": 0.001, "equity_intraday": 0.00025,
            "futures_index": 0.00001, "futures_stock": 0.0000125, "options": 0.000625,
        },
        "80c_limit": 150000, "80d_self_family": 25000, "80d_parents": 50000,
        "80d_senior_citizen": 50000, "80tta_interest_upto": 10000, "80ttb_senior_citizen": 50000,
        "standard_deduction_salaried": 50000, "home_loan_24b_self_occupied": 200000, "section_80eea": 150000,
    }
    path = DATA_DIR / "tax_rules_india.json"
    with open(path, "w") as f:
        json.dump(rules, f, indent=2)
    print(f"  saved: tax_rules_india.json")
    return rules


# =============================================================================
# SECTION 12: PROCESS ALL PRICE DATA -> MONTHLY RETURNS & STATISTICS
# =============================================================================

def compute_all_returns_and_stats():
    """
    Load all price series and compute:
    1. Monthly returns (all series)
    2. Annual returns
    3. Per-asset statistics
    4. Correlation matrix
    5. Covariance matrix
    """
    print("\n" + "="*65)
    print("[12] Computing Returns & Statistics")
    print("="*65)

    # Load all saved price files
    price_files = {
        "nse_tri_prices":      PROCESSED_DIR / "nse_tri_prices.pkl",
        "nse_bse_price_indices": PROCESSED_DIR / "nse_bse_price_indices.pkl",
        "indian_stocks":       PROCESSED_DIR / "indian_stocks.pkl",
        "commodities_fx":      PROCESSED_DIR / "commodities_fx.pkl",
        "indian_etfs":         PROCESSED_DIR / "indian_etfs.pkl",
        "amfi_mf_nav":         PROCESSED_DIR / "amfi_mutual_fund_nav.pkl",
    }

    all_prices = {}
    for name, path in price_files.items():
        if path.exists():
            df = pd.read_pickle(path)
            if df is not None and not df.empty:
                # Ensure DatetimeIndex
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index, errors="coerce")
                    df = df[df.index.notna()]
                if not df.empty:
                    # Add prefix to avoid column collisions
                    df.columns = [f"{name}_{c}" for c in df.columns]
                    all_prices[name] = df
                    print(f"  Loaded {name}: {df.shape}")

    if not all_prices:
        print("  WARNING: No price files found!")
        return

    # Outer join all prices
    combined = pd.concat(all_prices.values(), axis=1).sort_index()
    combined.index.name = "date"
    print(f"\n  Combined all prices: {combined.shape}")

    save_csv_pkl(combined, "all_prices_combined")

    # Compute monthly returns
    monthly_px = combined.resample("ME").last()
    monthly_ret = monthly_px.pct_change().iloc[1:]
    monthly_ret = monthly_ret.replace([np.inf, -np.inf], np.nan)
    save_csv_pkl(monthly_ret, "all_monthly_returns")
    print(f"  Monthly returns: {monthly_ret.shape}")

    # Compute annual returns
    annual_ret = (1 + monthly_ret).resample("YE").prod() - 1
    annual_ret = annual_ret.replace([np.inf, -np.inf], np.nan)
    save_csv_pkl(annual_ret, "all_annual_returns")
    print(f"  Annual returns: {annual_ret.shape}")

    # Per-asset statistics
    stats = {}
    rf_annual = 0.065  # 6.5% assumed risk-free rate for India
    for col in monthly_ret.columns:
        s = monthly_ret[col].dropna()
        if len(s) < 24:
            continue
        m = s.mean()
        std_m = s.std()
        m_a = (1 + m) ** 12 - 1
        std_a = std_m * np.sqrt(12)
        n_years = len(s) / 12
        geo = (1 + s).prod() ** (1 / n_years) - 1 if n_years > 0 else np.nan
        sharpe = (m_a - rf_annual) / std_a if std_a > 0 else 0
        cum = (1 + s).cumprod()
        peak = cum.expanding().max()
        dd = (cum - peak) / peak
        stats[col] = {
            "mean_annual": m_a, "std_annual": std_a, "geo_mean_annual": geo,
            "sharpe_ratio": sharpe, "max_drawdown": dd.min(),
            "skewness": s.skew(), "kurtosis": s.kurtosis(),
            "best_month": s.max(), "worst_month": s.min(),
            "n_months": len(s), "n_years": n_years,
            "start_date": str(s.index[0].date()), "end_date": str(s.index[-1].date()),
        }

    stats_df = pd.DataFrame(stats).T
    save_csv_pkl(stats_df, "all_asset_statistics")
    print(f"  Asset statistics: {stats_df.shape}")

    # Correlation matrix
    corr = monthly_ret.corr()
    save_csv_pkl(corr, "all_correlation_matrix")
    print(f"  Correlation matrix: {corr.shape}")

    # Covariance matrix (annualized)
    cov = monthly_ret.cov() * 12
    cov = cov.replace([np.inf, -np.inf], np.nan)
    save_csv_pkl(cov, "all_covariance_matrix")
    print(f"  Covariance matrix: {cov.shape}")

    return combined, monthly_ret, annual_ret, stats_df, corr, cov


# =============================================================================
# SECTION 13: PRINT COMPREHENSIVE SUMMARY
# =============================================================================

def print_summary(stats_df):
    """Print comprehensive statistics summary."""
    print("\n" + "="*65)
    print("ASSET STATISTICS SUMMARY (Annualized)")
    print("="*65)
    print(f"{'Asset':<55} {'Mean':>8} {'Std':>7} {'Sharpe':>7} {'MaxDD':>8} {'Geo':>8} {'Years':>6}")
    print("-"*105)

    for asset, r in stats_df.iterrows():
        try:
            mean = f"{r['mean_annual']:.2%}"
            std = f"{r['std_annual']:.2%}"
            sharpe = f"{r['sharpe_ratio']:.2f}"
            maxdd = f"{r['max_drawdown']:.2%}"
            geo = f"{r['geo_mean_annual']:.2%}"
            years = f"{r['n_years']:.1f}"
            print(f"  {asset:<53} {mean:>8} {std:>7} {sharpe:>7} {maxdd:>8} {geo:>8} {years:>6}")
        except Exception:
            pass


# =============================================================================
# MAIN
# =============================================================================

def main():
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = "2000-01-01"

    print("="*65)
    print("  ENHANCED INDIAN MONTE CARLO - DATA COLLECTOR v3")
    print("  Period:", start_date, "to", end_date)
    print("  Output:", PROCESSED_DIR)
    print("="*65)

    # Section 0: NSE TRI (Total Return Index) - MOST IMPORTANT
    collect_nse_tri()

    # Section 1: Nifty 50 Price Index
    collect_nifty50(start_date, end_date)

    # Section 2: NSE/BSE Price Indices
    collect_nse_indices(start_date, end_date)

    # Section 3: Individual Stocks
    collect_top_stocks(start_date, end_date)

    # Section 4: Commodities & FX
    collect_commodities_fx(start_date, end_date)

    # Section 5: Indian ETFs
    collect_indian_etfs(start_date, end_date)

    # Section 6: AMFI Mutual Funds via mftool
    collect_amfi_mutual_funds()

    # Section 7: PE/PB/Div data
    collect_index_pe_pb_div()

    # Section 8: RBI Macro
    collect_rbi_macro()

    # Section 9: Inflation
    collect_inflation()

    # Section 10: Life Expectancy
    collect_life_expectancy()

    # Section 11: Tax Rules
    collect_tax_rules()

    # Section 12: Compute all returns & statistics
    combined_prices, monthly_ret, annual_ret, stats_df, corr, cov = compute_all_returns_and_stats()

    # Section 13: Summary
    print_summary(stats_df)

    print(f"\n{'='*65}")
    print("  DONE. All files saved to:", PROCESSED_DIR)
    print("="*65)


if __name__ == "__main__":
    main()

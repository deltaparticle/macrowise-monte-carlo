#!/usr/bin/env python3
"""
Indian Market Data Collector v2
================================
Collects Indian market data from multiple sources:
1. Yahoo Finance - NSE/BSE indices, commodities, FX, ETFs
2. AMFI India - Mutual fund NAV data
3. RBI / FRED - Macroeconomic data

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
    csv = PROCESSED_DIR / f"{name}.csv"
    pkl = PROCESSED_DIR / f"{name}.pkl"
    df.to_csv(csv)
    df.to_pickle(pkl)
    print(f"  saved: {name} ({len(df)} rows x {len(df.columns)} cols)")
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
        return pd.DataFrame()


# =============================================================================
# 1. NIFTY 50 (benchmark)
# =============================================================================

def collect_nifty50(start="2000-01-01", end=None):
    print("[1] Nifty 50 (^NSEI)...", end=" ", flush=True)
    df = yf_download("^NSEI", start, end)
    if not df.empty:
        df.rename(columns={"Close": "NIFTY50"}, inplace=True)
        print(f"OK ({len(df)} rows)")
    else:
        print("FAILED")
    return df


# =============================================================================
# 2. NSE SECTORAL & MIDCAP INDICES
# =============================================================================

def collect_nse_sectoral(start="2000-01-01", end=None):
    """All NSE sectoral, midcap, smallcap indices via Yahoo Finance."""
    tickers = {
        "NIFTYBANK":   "^NSEBANK",
        "NIFTYIT":     "^CNXIT",
        "NIFTYPHARMA": "^CNXPHARMA",
        "NIFTYFMCG":   "^CNXFMCG",
        "NIFTYAUTO":   "^CNXAUTO",
        "NIFTYREALTY": "^CNXREALTY",
        "NIFTYFINNIFTY":"NIFTY_FIN_SERVICE.NS",
        "NIFTYMETAL":  "^CNXMETAL",
        "NIFTYENERGY": "^CNXENERGY",
        "NIFTYINFRA":  "^CNXINFRA",
        "NIFTYMIDCAP100": "^CRSMID",
    }

    print("[2] NSE Sectoral & Midcap...")
    results = {}

    for name, t in tickers.items():
        df = yf_download(t, start, end)
        if not df.empty:
            results[name] = df["Close"].rename(name)
            print(f"  {name}: OK ({len(df)})")
        else:
            print(f"  {name}: EMPTY")
        time.sleep(0.2)

    if results:
        combined = pd.DataFrame(results)
        combined.index.name = "date"
        combined = combined.sort_index()
        print(f"  combined: {combined.shape}")
        return combined
    return pd.DataFrame()


# =============================================================================
# 3. NIFTY SMALLCAP, NIFTY100, NIFTY200, NIFTY500
# =============================================================================

def collect_nse_broad(start="2000-01-01", end=None):
    """Nifty 100, 200, 500, Smallcap 100 via Yahoo Finance."""
    tickers = {
        "NIFTY100":       "^NSE100",
        "NIFTY200":       "^NSE200",
        "NIFTY500":       "^NSE500",
        "NIFTYSMALLCAP100": "^CRSML",
    }

    print("[3] NSE Broad Indices (100/200/500/Smallcap)...")
    results = {}

    for name, t in tickers.items():
        df = yf_download(t, start, end)
        if not df.empty:
            results[name] = df["Close"].rename(name)
            print(f"  {name}: OK ({len(df)})")
        else:
            print(f"  {name}: EMPTY")
        time.sleep(0.2)

    if results:
        combined = pd.DataFrame(results)
        combined.index.name = "date"
        combined = combined.sort_index()
        print(f"  combined: {combined.shape}")
        return combined
    return pd.DataFrame()


# =============================================================================
# 4. BSE INDICES
# =============================================================================

def collect_bse(start="2000-01-01", end=None):
    """BSE Sensex and related indices via Yahoo Finance."""
    tickers = {
        "SENSEX":     "^BSESN",
        "BSE_MIDCAP": "BSE-MIDCAP.NS",
        "BSE_SMALLCAP": "BSE-SMLCAP.NS",
        "BSE_500":    "BSE-500.NS",
    }

    print("[4] BSE Indices...")
    results = {}

    for name, t in tickers.items():
        df = yf_download(t, start, end)
        if not df.empty:
            results[name] = df["Close"].rename(name)
            print(f"  {name}: OK ({len(df)})")
        else:
            print(f"  {name}: EMPTY")
        time.sleep(0.2)

    if results:
        combined = pd.DataFrame(results)
        combined.index.name = "date"
        combined = combined.sort_index()
        print(f"  combined: {combined.shape}")
        return combined
    return pd.DataFrame()


# =============================================================================
# 5. INDIAN COMMODITY PRICES (GOLD / SILVER)
# =============================================================================

def collect_commodities(start="2000-01-01", end=None):
    """Gold, Silver, Crude, USDINR via Yahoo Finance."""
    tickers = {
        "GOLD_INR_ETF":  "GOLDBEES.NS",
        "SILVER_INR_ETF":"SILVERBEES.NS",
        "GOLD_USD_FUT":  "GC=F",
        "SILVER_USD_FUT":"SI=F",
        "CRUDE_WTI":     "CL=F",
        "CRUDE_BRENT":   "BZ=F",
        "USDINR":        "USDINR=X",
        "NIFTY_REALTY_ETF": "REALITY.NS",
    }

    print("[5] Commodities & FX...")
    results = {}

    for name, t in tickers.items():
        df = yf_download(t, start, end)
        if not df.empty:
            results[name] = df["Close"].rename(name)
            print(f"  {name}: OK ({len(df)})")
        else:
            print(f"  {name}: EMPTY")
        time.sleep(0.2)

    if results:
        combined = pd.DataFrame(results)
        combined.index.name = "date"
        combined = combined.sort_index()
        print(f"  combined: {combined.shape}")
        return combined
    return pd.DataFrame()


# =============================================================================
# 6. INDIAN ETF / MUTUAL FUND PROXIES
# =============================================================================

def collect_indian_etfs(start="2010-01-01", end=None):
    """Indian ETFs as asset class proxies via Yahoo Finance."""
    tickers = {
        # Nifty indices via ETFs
        "ETF_NIFTY50":             "NIFTYBEES.NS",
        "ETF_NIFTYBANK":           "BANKBEES.NS",
        "ETF_NIFTYIT":             "ITBEES.NS",
        # Gold & Silver
        "ETF_GOLD":                "GOLDBEES.NS",
        "ETF_SILVER":              "SILVERBEES.NS",
        # Liquid / Short-term
        "ETF_LIQUID":              "LIQUIDBEES.NS",
        "ETF_SHORT_TERM":          "SHORTBEES.NS",
        # Debt
        "ETF_GILT":                "GILT5YBEES.NS",
        # International
        "ETF_MOTILAL_NIFTY50":     "MON100.NS",
    }

    print("[6] Indian ETFs...")
    results = {}

    for name, t in tickers.items():
        df = yf_download(t, start, end)
        if not df.empty:
            results[name] = df["Close"].rename(name)
            print(f"  {name}: OK ({len(df)})")
        else:
            print(f"  {name}: EMPTY")
        time.sleep(0.2)

    if results:
        combined = pd.DataFrame(results)
        combined.index.name = "date"
        combined = combined.sort_index()
        print(f"  combined: {combined.shape}")
        return combined
    return pd.DataFrame()


# =============================================================================
# 7. CPI INFLATION
# =============================================================================

def collect_cpi_inflation():
    """India CPI - FRED + RBI fallback."""
    print("[7] CPI Inflation...")
    results = {}

    # FRED: INDCPIALLMINMEI
    try:
        import pandas_datareader.data as web
        cpi = web.DataReader("INDCPIALLMINMEI", "fred", "2000-01-01", "2026-06-30")
        if not cpi.empty:
            cpi.columns = ["CPI_Index"]
            cpi["CPI_MoM"] = cpi["CPI_Index"].pct_change()
            cpi["CPI_YoY"] = cpi["CPI_Index"].pct_change(12)
            results["CPI_FRED"] = cpi
            print(f"  CPI (FRED): OK ({len(cpi)} rows)")
    except Exception as e:
        print(f"  CPI (FRED): {e}")

    # FRED: India 10Y bond yield
    try:
        bond_yield = web.DataReader("INDIRLTLT01STM", "fred", "2000-01-01", "2026-06-30")
        if not bond_yield.empty:
            bond_yield.columns = ["India_10Y_Yield"]
            results["Bond_Yield"] = bond_yield
            print(f"  Bond Yield (FRED): OK ({len(bond_yield)} rows)")
    except Exception as e:
        print(f"  Bond Yield (FRED): {e}")

    # Combine
    if results:
        # Separate to avoid column conflicts
        all_dfs = []
        for k, v in results.items():
            if isinstance(v, pd.DataFrame) and v.select_dtypes(include="number").shape[1] > 0:
                prefixed = v.add_prefix(f"{k}_")
                prefixed.index.name = "date"
                all_dfs.append(prefixed)

        if all_dfs:
            combined = pd.concat(all_dfs, axis=1)
            save_csv_pkl(combined, "cpi_data")
            return combined
    return pd.DataFrame()


# =============================================================================
# 8. RBI POLICY RATES
# =============================================================================

def collect_rbi_policy_rates():
    """RBI repo rate history (compiled from published data)."""
    print("[8] RBI Policy Rates...")

    repo_history = {
        "2000-01": 6.50,  "2000-03": 9.00,  "2000-04": 9.50,  "2000-08": 8.50,
        "2001-02": 6.50,  "2001-03": 6.00,  "2001-11": 5.50,
        "2002-01": 5.50,  "2002-03": 5.00,  "2002-09": 4.50,  "2002-12": 4.30,
        "2003-03": 4.30,  "2003-10": 4.00,  "2003-12": 3.90,
        "2004-01": 3.70,  "2004-03": 3.50,  "2004-10": 3.25,  "2004-12": 3.00,
        "2005-01": 3.00,  "2005-03": 2.75,  "2005-10": 2.50,
        "2006-01": 2.50,  "2006-06": 2.75,  "2006-07": 3.00,  "2006-08": 3.25,
        "2006-10": 3.75,  "2006-11": 4.00,  "2006-12": 4.25,
        "2007-01": 4.50,  "2007-02": 4.75,  "2007-03": 5.00,  "2007-04": 5.25,
        "2007-06": 5.50,  "2007-07": 5.75,  "2007-10": 6.00,
        "2008-01": 6.00,  "2008-03": 7.25,  "2008-04": 8.00,  "2008-07": 8.50,  "2008-10": 9.00,
        "2009-03": 5.00,  "2009-04": 4.50,  "2009-11": 4.25,
        "2010-01": 5.00,  "2010-03": 5.25,  "2010-09": 6.00,  "2010-11": 6.25,
        "2011-01": 6.50,  "2011-03": 7.25,  "2011-06": 7.50,  "2011-09": 8.00,
        "2011-10": 8.25,  "2011-11": 8.50,  "2012-01": 8.50,  "2012-04": 8.00,
        "2012-06": 8.00,  "2012-09": 7.50,  "2012-11": 7.25,
        "2013-02": 7.25,  "2013-04": 7.00,  "2013-09": 6.75,  "2013-10": 6.50,
        "2013-11": 6.50,  "2013-12": 6.50,
        "2014-01": 6.50,  "2014-03": 6.25,  "2014-06": 6.00,  "2014-09": 5.75,
        "2015-03": 5.75,  "2015-06": 5.50,  "2015-09": 5.25,
        "2016-01": 5.75,  "2016-03": 5.50,  "2016-06": 5.25,
        "2017-08": 5.00,  "2017-11": 4.75,
        "2018-06": 6.00,  "2018-08": 6.50,  "2018-10": 7.25,
        "2019-02": 6.25,  "2019-04": 6.00,  "2019-06": 5.75,  "2019-08": 5.50,  "2019-10": 5.25,
        "2020-03": 4.40,  "2020-05": 4.00,  "2020-07": 3.50,  "2020-10": 3.00,
        "2021-05": 4.00,  "2021-08": 4.25,  "2021-12": 4.50,
        "2022-05": 4.50,  "2022-06": 4.25,  "2022-08": 4.00,  "2022-09": 3.75,
        "2022-10": 3.50,  "2022-11": 3.50,  "2022-12": 3.50,
        "2023-01": 3.50,  "2023-02": 3.50,  "2023-04": 3.25,  "2023-05": 3.00,  "2023-06": 3.00,
        "2023-08": 3.00,  "2023-10": 2.75,  "2023-12": 2.50,
        "2024-02": 3.25,  "2024-04": 3.00,  "2024-06": 3.00,  "2024-08": 2.75,
        "2024-10": 2.75,  "2024-12": 2.50,
        "2025-02": 2.50,  "2025-04": 2.50,  "2025-06": 2.50,  "2025-10": 2.50,
        "2026-01": 2.50,
    }

    df = pd.DataFrame(list(repo_history.items()), columns=["month", "repo_rate_pct"])
    df["date"] = pd.to_datetime(df["month"])
    df = df.set_index("date").drop(columns=["month"])
    df["repo_rate"] = df["repo_rate_pct"] / 100.0
    df = df.resample("ME").ffill()
    df.drop(columns=["repo_rate_pct"], inplace=True)

    save_csv_pkl(df, "rbi_repo_rate_history")
    return df


# =============================================================================
# 9. TAX RULES
# =============================================================================

def collect_tax_rules():
    """Save Indian tax rules as JSON."""
    print("[9] Tax Rules...")

    rules = {
        "description": "Indian income tax rules for Monte Carlo simulation",
        "fy": "FY 2024-25 (AY 2025-26)",
        "source": "Income Tax Act 1961, Finance Act 2024, Budget 2024",
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
        "dividend_tax": {
            "ddt_abolished": True,
            "tax_free_upto": 10000000,
            "above_10L_rate": 0.10,
            "tds_rate": 0.10,
        },
        "nps": {
            "tier1_self_80ccd1b": 50000,
            "tier1_total_80ccd1": 200000,
            "tax_free_at_maturity_pct": 60.0,
            "annuity_40pct_mandatory": True,
        },
        "epf": {
            "employee_80c": True,
            "employer_tax_free_upto": 250000,
            "interest_rate": 0.0825,
        },
        "ppf": {
            "deduction_limit_80c": 150000,
            "interest_rate": 0.075,
            "interest_tax_free": True,
        },
        "stt_rates": {
            "equity_delivery": 0.001,
            "equity_intraday": 0.00025,
            "futures_index": 0.00001,
            "futures_stock": 0.0000125,
            "options": 0.000625,
        },
        "80c_limit": 150000,
        "80d_self_family": 25000,
        "80d_parents": 50000,
        "80d_senior_citizen": 50000,
        "80tta_interest_upto": 10000,
        "80ttb_senior_citizen": 50000,
        "standard_deduction_salaried": 50000,
        "home_loan_24b_self_occupied": 200000,
        "section_80eea": 150000,
    }

    path = DATA_DIR / "tax_rules_india.json"
    with open(path, "w") as f:
        json.dump(rules, f, indent=2)
    print(f"  saved: {path}")
    return rules


# =============================================================================
# 10. LIFE EXPECTANCY
# =============================================================================

def collect_life_expectancy():
    """Save Indian life expectancy data."""
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

    meta = {k: v for k, v in data.items() if k != "data"}
    with open(DATA_DIR / "life_expectancy_metadata.json", "w") as f:
        json.dump(meta, f, indent=2)

    return df


# =============================================================================
# 11. AMFI MUTUAL FUND NAV
# =============================================================================

def collect_amfi_nav():
    """Collect AMFI mutual fund NAV via scheme history API."""
    print("[11] AMFI Mutual Fund NAV...")

    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://www.amfiindia.com/"})

        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=365 * 10)

        schemes = {
            "AMFI_AxisBluechip": "119275",
            "AMFI_MiraeLargecap": "118525",
            "AMFI_UTINifty50": "148524",
            "AMFI_HDFCTop100": "119034",
            "AMFI_KotakMidcap": "119355",
            "AMFI_SBISmallCap": "119218",
            "AMFI_ParagParikhFlexi": "119423",
            "AMFI_MiraeTaxSaver": "119520",
            "AMFI_ICICIEquityDebt": "119261",
            "AMFI_ICICIConservative": "119582",
            "AMFI_ICICIBalancedAdv": "119588",
            "AMFI_NipponLiquid": "119553",
            "AMFI_FranklinUltraShort": "119269",
            "AMFI_ICICICorpBond": "119524",
            "AMFI_SBIGilt": "119597",
            "AMFI_ICICIDynamicBond": "119388",
        }

        results = {}
        for name, code in schemes.items():
            params = {
                "mf": code,
                "frmdt": start_dt.strftime("%d-%b-%Y"),
                "todt": end_dt.strftime("%d-%b-%Y"),
            }
            try:
                resp = session.get(
                    "https://www.amfiindia.com/spages/NAVHistoryReport.aspx",
                    params=params, timeout=30
                )
                if resp.status_code == 200:
                    df = pd.read_csv(
                        StringIO(resp.text), skiprows=1,
                        names=["Date", "NAV", "Repurchase", "SalePrice"],
                        on_bad_lines="skip"
                    )
                    df["Date"] = pd.to_datetime(df["Date"], format="%d-%b-%Y", errors="coerce")
                    df["NAV"] = pd.to_numeric(df["NAV"], errors="coerce")
                    df = df.dropna(subset=["NAV"]).sort_values("Date")
                    if not df.empty:
                        results[name] = df.set_index("Date")["NAV"]
                        print(f"  {name}: OK ({len(df)} rows)")
                    else:
                        print(f"  {name}: EMPTY")
                else:
                    print(f"  {name}: HTTP {resp.status_code}")
            except Exception as e:
                print(f"  {name}: {e}")
            time.sleep(0.5)

        if results:
            combined = pd.DataFrame(results)
            combined.index.name = "date"
            combined = combined.sort_index()
            save_csv_pkl(combined, "amfi_mf_nav")
            return combined
    except Exception as e:
        print(f"  Error: {e}")
    return pd.DataFrame()


# =============================================================================
# 12. PROCESS: MONTHLY RETURNS & STATISTICS
# =============================================================================

def compute_monthly_returns(price_df):
    """Daily prices -> monthly returns. Keeps row if any asset has valid return."""
    if price_df.empty:
        return pd.DataFrame()
    # Last price of each month
    monthly_px = price_df.resample("ME").last()
    # pct_change per column
    monthly_ret = monthly_px.pct_change()
    # Drop the first row (NaN from pct_change) but keep sparse data
    monthly_ret = monthly_ret.iloc[1:]
    return monthly_ret


def compute_annual_returns(monthly_df):
    """Monthly returns -> annual returns."""
    if monthly_df.empty:
        return pd.DataFrame()
    annual = (1 + monthly_df).resample("YE").prod() - 1
    return annual


def compute_statistics(monthly_df, rf_annual=0.065):
    """Key stats for each asset class."""
    if monthly_df.empty:
        return pd.DataFrame()

    stats = {}
    for col in monthly_df.columns:
        s = monthly_df[col].dropna()  # drop only NaN for this column
        if len(s) < 24:
            continue

        m = s.mean()
        std_m = s.std()
        m_a = (1 + m) ** 12 - 1
        std_a = std_m * np.sqrt(12)
        geo = (1 + s).prod() ** (1 / (len(s) / 12)) - 1
        sharpe = (m_a - rf_annual) / std_a if std_a > 0 else 0

        cum = (1 + s).cumprod()
        peak = cum.expanding().max()
        dd = (cum - peak) / peak

        stats[col] = {
            "mean_monthly": m, "std_monthly": std_m,
            "mean_annual": m_a, "std_annual": std_a,
            "geo_mean_annual": geo, "sharpe_ratio": sharpe,
            "max_drawdown": dd.min(), "skewness": s.skew(), "kurtosis": s.kurtosis(),
            "n_months": len(s), "n_years": len(s) / 12,
            "start": str(s.index[0].date()), "end": str(s.index[-1].date()),
            "best_month": s.max(), "worst_month": s.min(),
        }

    df = pd.DataFrame(stats).T
    df.index.name = "asset"
    col_order = ["mean_annual","std_annual","geo_mean_annual","sharpe_ratio",
                 "max_drawdown","skewness","kurtosis",
                 "best_month","worst_month","n_months","n_years","start","end"]
    return df[[c for c in col_order if c in df.columns]]


def print_summary(stats):
    """Pretty print stats table."""
    if stats.empty:
        print("  (no data)")
        return
    print()
    for asset, r in stats.iterrows():
        print(f"  {asset:40s}  mean={r['mean_annual']:>8.2%}  std={r['std_annual']:>7.2%}  "
              f"sharpe={r['sharpe_ratio']:>5.2f}  maxdd={r['max_drawdown']:>7.2%}  "
              f"geo={r['geo_mean_annual']:>7.2%}  ({r['start']} to {r['end']})")


# =============================================================================
# MAIN
# =============================================================================

def main():
    end = datetime.now().strftime("%Y-%m-%d")
    start = "2000-01-01"

    print("=" * 65)
    print(f"  INDIAN MONTE CARLO - DATA COLLECTOR")
    print(f"  Period: {start} to {end}")
    print(f"  Output: {DATA_DIR}")
    print("=" * 65)

    # Check deps
    try:
        import yfinance
        print(f"  yfinance: {yfinance.__version__}")
    except ImportError:
        os.system("pip install yfinance pandas-datareader -q")
        import yfinance

    all_data = {}

    # 1. Nifty 50
    all_data["nifty50"] = collect_nifty50(start, end)

    # 2. NSE Sectoral
    all_data["nse_sectoral"] = collect_nse_sectoral(start, end)

    # 3. NSE Broad
    all_data["nse_broad"] = collect_nse_broad(start, end)

    # 4. BSE
    all_data["bse"] = collect_bse(start, end)

    # 5. Commodities & FX
    all_data["commodities"] = collect_commodities(start, end)

    # 6. Indian ETFs
    all_data["etfs"] = collect_indian_etfs(start, end)

    # 7. CPI
    all_data["cpi"] = collect_cpi_inflation()

    # 8. RBI Policy Rates
    all_data["repo_rate"] = collect_rbi_policy_rates()

    # 9. Tax Rules
    all_data["tax"] = collect_tax_rules()

    # 10. Life Expectancy
    all_data["life_exp"] = collect_life_expectancy()

    # 11. AMFI NAV
    all_data["amfi"] = collect_amfi_nav()

    # ========== Combine & Process ==========
    print("\n[COMBINE] Merging price data...")

    # Only include actual time-series price DataFrames (exclude metadata like life expectancy)
    # Also ensure index is a proper DatetimeIndex
    price_frames = {}
    for k, v in all_data.items():
        if isinstance(v, pd.DataFrame) and not v.empty:
            # Skip non-price data (life expectancy is just 15 rows of static data)
            if len(v) < 50:
                continue
            # Ensure DatetimeIndex
            if not isinstance(v.index, pd.DatetimeIndex):
                v.index = pd.to_datetime(v.index, errors="coerce")
                v = v[v.index.notna()]
            if not v.empty:
                price_frames[k] = v

    if not price_frames:
        print("  WARNING: No price data collected!")
        return

    # Rename columns with prefix, then concat on outer join
    prefixed = []
    for k, v in price_frames.items():
        df = v.copy()
        df.columns = [f"{k}_{c}" for c in v.columns]
        df = df.sort_index()
        prefixed.append(df)

    combined = pd.concat(prefixed, axis=1, join="outer")
    combined.index.name = "date"
    combined = combined.sort_index()

    save_csv_pkl(combined, "all_prices")
    print(f"\n  Combined shape: {combined.shape}")

    # Monthly returns
    monthly = compute_monthly_returns(combined)
    save_csv_pkl(monthly, "indian_monthly_returns")
    print(f"  Monthly returns: {monthly.shape}")

    # Annual returns
    annual = compute_annual_returns(monthly)
    save_csv_pkl(annual, "indian_annual_returns")
    print(f"  Annual returns: {annual.shape}")

    # Statistics
    stats = compute_statistics(monthly)
    save_csv_pkl(stats, "indian_asset_statistics")
    print(f"  Statistics: {stats.shape}")

    # Correlation
    corr = monthly.corr()
    save_csv_pkl(corr, "indian_correlation_matrix")
    print(f"  Correlation: {corr.shape}")

    # Covariance (annualized)
    cov = monthly.cov() * 12
    save_csv_pkl(cov, "indian_covariance_matrix")
    print(f"  Covariance: {cov.shape}")

    # ========== Summary ==========
    print("\n[ASSET STATISTICS SUMMARY]")
    print_summary(stats)

    print(f"\n{'='*65}")
    print(f"  DONE. All files in {PROCESSED_DIR}")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()

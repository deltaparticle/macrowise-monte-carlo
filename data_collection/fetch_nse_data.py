#!/usr/bin/env python3
"""
NSE India Data Fetcher
======================
Specialized fetcher for NSE equity index historical data.
Uses multiple approaches to maximize data collection:
1. NSE India public API
2. Yahoo Finance fallback
3. Manual CSV download instructions

Supported Indices:
- Broad: Nifty 50, 100, 200, 500
- Market Cap: Midcap 100, Smallcap 100, Microcap 250
- Sectoral: Bank, IT, Pharma, FMCG, Auto, Infra, Realty, Financial Services, Metal, Energy
- Strategy: Dividend Opps, Growth Sectors, Quality 30, Value 20, Momentum 50
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests


def save_dataframe(df, name, processed=True):
    """Save a DataFrame to both CSV and pickle."""
    out_dir = PROCESSED_DIR if processed else RAW_DIR
    csv_path = out_dir / f"{name}.csv"
    pkl_path = out_dir / f"{name}.pkl"

    df.to_csv(csv_path)
    df.to_pickle(pkl_path)
    print(f"  Saved {name}: {csv_path} ({len(df)} rows)")
    return csv_path


# =============================================================================
# CONFIG
# =============================================================================
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

for d in [DATA_DIR, RAW_DIR, PROCESSED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
}

# Mapping of our keys to NSE API symbols
NSE_SYMBOL_MAP = {
    "NIFTY50": "NIFTY 50",
    "NIFTY100": "NIFTY 100",
    "NIFTY200": "NIFTY 200",
    "NIFTY500": "NIFTY 500",
    "NIFTYMIDCAP100": "NIFTY MIDCAP 100",
    "NIFTYMIDCAP50": "NIFTY MIDCAP 50",
    "NIFTYSMALLCAP100": "NIFTY SMALLCAP 100",
    "NIFTYMICROCAP250": "NIFTY MICROCAP 250",
    "NIFTYBANK": "NIFTY BANK",
    "NIFTYIT": "NIFTY IT",
    "NIFTYPHARMA": "NIFTY PHARMA",
    "NIFTYFMCG": "NIFTY FMCG",
    "NIFTYAUTO": "NIFTY AUTO",
    "NIFTYINFRA": "NIFTY INFRA",
    "NIFTYREALTY": "NIFTY REALTY",
    "NIFTYFINNIFTY": "NIFTY FINNIFTY",
    "NIFTYMETAL": "NIFTY METAL",
    "NIFTYENERGY": "NIFTY ENERGY",
    "NIFTYDIVOPPS50": "NIFTY DIVIDEND OPPORTUNITIES 50",
    "NIFTYGROWSECT15": "NIFTY GROWTH SECTORS 15",
    "NIFTY100QUALITY30": "NIFTY 100 QUALITY 30",
    "NIFTY50VALUE20": "NIFTY 50 VALUE 20",
    "NIFTYMOMENTUM50": "NIFTY MOMENTUM 50",
}

# G-Sec Indices
GSEC_SYMBOL_MAP = {
    "NIFTYGOVT10YR": "NIFTY 10 YR G-SEC INDEX",
    "NIFTYGOVT4TO6YR": "NIFTY 4-6 YR G-SEC INDEX",
    "NIFTYGOVT6TO8YR": "NIFTY 6-8 YR G-SEC INDEX",
    "NIFTYGOVT8TO10YR": "NIFTY 8-10 YR G-SEC INDEX",
    "NIFTYGOVTLONG": "NIFTY LONG TERM G-SEC INDEX",
    "NIFTYGOVTSHORT": "NIFTY SHORT TERM G-SEC INDEX",
    "NIFTYGOVTSUPRA": "NIFTY G-SEC SUPRA INDEX",
    "NIFTYCORPBOND": "NIFTY CORPORATE BOND INDEX",
    "NIFTYLIQ12": "NIFTY 1D LIQUID INDEX",
    "NIFTYULTRASHORT": "NIFTY ULTRA SHORT TERM BOND INDEX",
}


def get_session() -> requests.Session:
    """Create and return a configured NSE session."""
    s = requests.Session()
    s.headers.update(HEADERS)
    # Warm up the session by visiting the homepage first
    try:
        s.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
    except Exception:
        pass
    return s


def fetch_nse_index(session: requests.Session, symbol: str, start: str, end: str) -> pd.Series:
    """Fetch a single NSE index using the NSE API."""
    try:
        url = "https://www.nseindia.com/api/historical/indices/historical"
        params = {
            "symbol": symbol,
            "from": start,
            "to": end,
        }

        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        records = data.get("data", [])
        if not records:
            return pd.Series(dtype=float, name=symbol)

        df = pd.DataFrame(records)
        # Find the close column
        close_col = None
        date_col = None
        for col in df.columns:
            col_clean = col.strip().lower()
            if "close" in col_clean:
                close_col = col
            if "date" in col_clean:
                date_col = col

        if close_col and date_col:
            df = df[[date_col, close_col]].copy()
            df[date_col] = pd.to_datetime(df[date_col])
            df[close_col] = pd.to_numeric(df[close_col], errors="coerce")
            df = df.dropna(subset=[close_col])
            df.set_index(date_col, inplace=True)
            df.index.name = "date"
            series = df[close_col]
            series.name = symbol
            return series

        return pd.Series(dtype=float, name=symbol)

    except Exception as e:
        return pd.Series(dtype=float, name=symbol)


def fetch_yfinance_fallback(ticker: str, start: str, end: str) -> pd.Series:
    """Fallback to Yahoo Finance for any index."""
    try:
        import yfinance as yf

        df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        if not df.empty:
            series = df["Close"].copy()
            series.name = ticker
            return series
    except Exception:
        pass
    return pd.Series(dtype=float, name=ticker)


def collect_equity_indices(start: str = "2000-01-01", end: str = None) -> pd.DataFrame:
    """
    Collect all NSE equity indices.

    Args:
        start: Start date string YYYY-MM-DD
        end: End date string YYYY-MM-DD (default: today)
    """
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    print(f"[NSE] Collecting equity indices from {start} to {end}")

    session = get_session()
    all_series = {}

    for key, symbol in NSE_SYMBOL_MAP.items():
        print(f"  {symbol}...", end=" ", flush=True)

        # Try NSE API first
        series = fetch_nse_index(session, symbol, start, end)

        if series.empty or len(series) < 50:
            # Try alternate NSE symbol format
            alt_symbol = key  # Some indices use their key name
            series = fetch_nse_index(session, alt_symbol, start, end)

        if series.empty or len(series) < 50:
            # Try Yahoo Finance
            yf_map = {
                "NIFTY50": "^NSEI",
                "NIFTYBANK": "^NSEBANK",
                "NIFTYIT": "^CNXIT",
                "NIFTYMIDCAP100": "^CRSMID",
                "NIFTYSMALLCAP100": "^CRSML",
                "NIFTYMETAL": "^CNXMETAL",
                "NIFTYPHARMA": "^CNXPHARMA",
                "NIFTYFMCG": "^CNXFMCG",
                "NIFTYAUTO": "^CNXAUTO",
                "NIFTYREALTY": "^CNXREALTY",
                "NIFTYENERGY": "^CNXENERGY",
                "NIFTYINFRA": "^CNXINFRA",
                "NIFTYFINNIFTY": "NIFTY_FIN_SERVICE.NS",
                "NIFTY200": "^NSE200",
            }
            yf_ticker = yf_map.get(key)
            if yf_ticker:
                series = fetch_yfinance_fallback(yf_ticker, start, end)

        if not series.empty:
            print(f"OK ({len(series)} rows, {series.index[0].date()} to {series.index[-1].date()})")
        else:
            print("FAILED")

        all_series[key] = series
        time.sleep(1.2)  # Rate limiting for NSE

    # Combine into DataFrame
    combined = pd.DataFrame(all_series)
    combined.index.name = "date"
    combined = combined.sort_index()

    # Save
    save_dataframe(combined, "nse_equity_indices")
    return combined


def collect_gsec_indices(start: str = "2000-01-01", end: str = None) -> pd.DataFrame:
    """Collect G-Sec bond indices."""
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    print(f"[NSE] Collecting G-Sec indices from {start} to {end}")

    session = get_session()
    all_series = {}

    for key, symbol in GSEC_SYMBOL_MAP.items():
        print(f"  {symbol}...", end=" ", flush=True)
        series = fetch_nse_index(session, symbol, start, end)

        if not series.empty:
            print(f"OK ({len(series)} rows)")
        else:
            print("FAILED")

        all_series[key] = series
        time.sleep(1.2)

    combined = pd.DataFrame(all_series)
    combined.index.name = "date"
    combined = combined.sort_index()
    save_dataframe(combined, "nse_gsec_indices")
    return combined


def fetch_with_retry(fetch_fn, max_retries: int = 3, delay: float = 5.0):
    """Generic retry wrapper for fetch functions."""
    for attempt in range(max_retries):
        try:
            result = fetch_fn()
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Retrying ({attempt + 1}/{max_retries}) after {delay}s: {e}")
                time.sleep(delay)
            else:
                print(f"  Failed after {max_retries} attempts")
    return pd.DataFrame()


def download_nse_bhavcopy(date_str: str) -> pd.DataFrame:
    """
    Download NSE Bhavcopy (EOD data) for a specific date.
    Useful as an alternate data source.
    """
    try:
        url = f"https://www.nseindia.com/content/historical/EQUITIES/{date_str[:4]}/{date_str[5:7].upper()}/cm{date_str.replace('-', '')}bhav.csv.zip"
        resp = requests.get(url, headers=HEADERS, timeout=30)
        return pd.read_csv(url)
    except Exception as e:
        print(f"  Bhavcopy download failed: {e}")
        return pd.DataFrame()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2000-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--equity", action="store_true")
    parser.add_argument("--gsec", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.end is None:
        args.end = datetime.now().strftime("%Y-%m-%d")

    if args.all or args.equity:
        collect_equity_indices(args.start, args.end)
    if args.all or args.gsec:
        collect_gsec_indices(args.start, args.end)

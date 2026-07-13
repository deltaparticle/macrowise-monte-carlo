"""Download daily OHLC+Return data for all Nifty 500 constituents via yfinance.

Reads `ind_nifty500list.csv`, downloads each ticker as `SYMBOL.NS`, saves one
CSV per stock in `data_stocks_nifty500/`. Preserves the same schema as
`data_index level/*_yfinance.csv` files:
  columns: Date, Open, High, Low, Close, Return, Volatility

Batches downloads via yfinance's built-in threaded downloader for speed.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

LIST_CSV = Path("ind_nifty500list.csv")
OUT_DIR = Path("data_stocks_nifty500")
OUT_DIR.mkdir(exist_ok=True)
FAIL_LOG = OUT_DIR / "download_failures.json"
META_CSV = OUT_DIR / "metadata.csv"

START = "2000-01-01"
END = None  # today
BATCH_SIZE = 50


def compute_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Compute daily Return and rolling 30-day Volatility columns."""
    df = df.copy()
    df["Return"] = df["Close"].pct_change()
    df["Volatility"] = df["Return"].rolling(window=30).std()
    return df


def main():
    print(f"Reading {LIST_CSV}...")
    stocks = pd.read_csv(LIST_CSV)
    print(f"  {len(stocks)} stocks")

    symbols = stocks["Symbol"].str.strip().tolist()
    tickers = [f"{s}.NS" for s in symbols]
    industry_map = dict(zip(stocks["Symbol"], stocks["Industry"]))
    name_map = dict(zip(stocks["Symbol"], stocks["Company Name"]))

    # Skip any already downloaded (idempotent)
    existing = {p.stem.replace("_yfinance", "") for p in OUT_DIR.glob("*_yfinance.csv")}
    todo = [(s, t) for s, t in zip(symbols, tickers) if s not in existing]
    print(f"  Already downloaded: {len(existing)}. To download: {len(todo)}")

    failures = []
    successes = []
    if FAIL_LOG.exists():
        try:
            failures = json.loads(FAIL_LOG.read_text())
        except Exception:
            failures = []

    # Batch download
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        batch_tickers = [t for _, t in batch]
        batch_symbols = [s for s, _ in batch]
        print(f"[{i}-{i + len(batch)}/{len(todo)}] downloading {len(batch)} tickers...")

        try:
            data = yf.download(
                batch_tickers,
                start=START,
                end=END,
                progress=False,
                threads=True,
                group_by="ticker",
                auto_adjust=False,
            )
        except Exception as e:
            print(f"  batch failed entirely: {e}")
            failures.extend([{"symbol": s, "ticker": t, "error": str(e)}
                             for s, t in batch])
            time.sleep(3)
            continue

        # data is a wide MultiIndex DataFrame: (ticker, ohlcv) columns
        for sym, tick in batch:
            try:
                if len(batch_tickers) == 1:
                    df = data.copy()
                else:
                    if tick not in data.columns.get_level_values(0):
                        raise KeyError(f"No data for {tick}")
                    df = data[tick].copy()
                if df.empty or df.dropna(how="all").empty:
                    raise ValueError("empty data")
                df = df.reset_index()
                # yfinance uses "Date" already
                keep = [c for c in ["Date", "Open", "High", "Low", "Close"]
                        if c in df.columns]
                df = df[keep]
                df = df.dropna(subset=["Close"])
                if len(df) < 60:
                    raise ValueError(f"only {len(df)} rows")
                df = compute_returns(df)
                out = OUT_DIR / f"{sym}_yfinance.csv"
                df.to_csv(out, index=False)
                successes.append({"symbol": sym, "rows": len(df),
                                  "start": str(df["Date"].iloc[0]),
                                  "end": str(df["Date"].iloc[-1]),
                                  "industry": industry_map.get(sym, "Unknown"),
                                  "name": name_map.get(sym, sym)})
            except Exception as e:
                failures.append({"symbol": sym, "ticker": tick, "error": str(e)})

        # Persist progress
        FAIL_LOG.write_text(json.dumps(failures, indent=2, default=str))
        if successes:
            pd.DataFrame(successes).to_csv(META_CSV, index=False)
        time.sleep(1)  # be gentle with yahoo

    # Final metadata (rebuild from filesystem in case script was rerun)
    print("\nRebuilding metadata from filesystem...")
    all_meta = []
    for csv in sorted(OUT_DIR.glob("*_yfinance.csv")):
        sym = csv.stem.replace("_yfinance", "")
        try:
            df = pd.read_csv(csv, nrows=0)
            df_full = pd.read_csv(csv, usecols=["Date"])
            all_meta.append({
                "symbol": sym,
                "rows": len(df_full),
                "start": df_full["Date"].iloc[0] if len(df_full) else "",
                "end": df_full["Date"].iloc[-1] if len(df_full) else "",
                "industry": industry_map.get(sym, "Unknown"),
                "name": name_map.get(sym, sym),
            })
        except Exception:
            pass
    pd.DataFrame(all_meta).to_csv(META_CSV, index=False)

    print(f"\nDone. Successes: {len(all_meta)}. Failures: {len(failures)}")
    if failures:
        print("Failed symbols:", [f["symbol"] for f in failures[:10]], "...")


if __name__ == "__main__":
    main()

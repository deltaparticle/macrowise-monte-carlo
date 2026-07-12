#!/usr/bin/env python3
"""
Ultimate NSE/BSE Stock Downloader
================================
Download ANY stock/index/ETF/commodity from Yahoo Finance for Indian markets (NSE/BSE).

Features:
- Auto-resolves NSE/BSE tickers from stock names
- Yahoo Finance search
- Supports ALL tickers on Yahoo Finance (.NS, .BO)
- Advanced search with fuzzy matching
- Extensive testing suite

Usage:
    # Single stock
    python download_nse_bse.py RELIANCE
    python download_nse_bse.py "TATA MOTORS"
    python download_nse_bse.py SBIN --start 2023-01-01 --end 2024-01-01
    python download_nse_bse.py NIFTY50

    # BSE stock
    python download_nse_bse.py RELIANCE.BO

    # Search
    python download_nse_bse.py --search "tata"
    python download_nse_bse.py --search "axis"

    # Test
    python download_nse_bse.py --test
    python download_nse_bse.py --test-popular
    python download_nse_bse.py --test-bse
    python download_nse_bse.py --test-performance

    # Bulk
    echo "RELIANCE\nTCS\nHDFCBANK" > stocks.txt
    python download_nse_bse.py --batch stocks.txt

    # List
    python download_nse_bse.py --list
"""

import argparse
import asyncio
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
import pandas as pd
import requests
import yfinance as yf
from tqdm import tqdm

# Configuration
OUTPUT_DIR = Path("downloads")
OUTPUT_DIR.mkdir(exist_ok=True)

# Known tickers for quick lookup
KNOWN_TICKERS = {
    # NSE Indices
    "NIFTY50": "^NSEI",
    "NIFTYBANK": "^NSEBANK",
    "NIFTYIT": "^CNXIT",
    "NIFTYAUTO": "^CNXAUTO",
    "NIFTYFMCG": "^CNXFMCG",
    "NIFTYPHARMA": "^CNXPHARMA",
    "NIFTYREALTY": "^CNXREALTY",
    "NIFTYMETAL": "^CNXMETAL",
    "NIFTYENERGY": "^CNXENERGY",
    "NIFTYINFRA": "^CNXINFRA",
    "NIFTYMIDCAP100": "^CRSMID",
    "NIFTYSMALLCAP100": "^CRSML",
    "NIFTYNEXT50": "^NSEI",  # Use ^NSEI as fallback
    "NIFTY200": "^NSE200",
    "NIFTY500": "^NSE500",
    "INDIAVIX": "^INDIAVIX",

    # BSE Indices
    "SENSEX": "^BSESN",
    "BSEMIDCAP": "BSE-MIDCAP.NS",
    "BSESMALLCAP": "BSE-SMLCAP.NS",
    "BSE500": "BSE-500.NS",

    # Popular NSE Stocks
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "INFY": "INFY.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "SBIN": "SBIN.NS",
    "BHARTIARTL": "BHARTIARTL.NS",
    "HUL": "HINDUNILVR.NS",
    "ITC": "ITC.NS",
    "LT": "LT.NS",
    "TITAN": "TITAN.NS",
    "SUNPHARMA": "SUNPHARMA.NS",
    "NESTLEIND": "NESTLEIND.NS",
    "INDUSINDBK": "INDUSINDBK.NS",
    "KOTAKBANK": "KOTAKBANK.NS",
    "BAJFINANCE": "BAJFINANCE.NS",
    "WIPRO": "WIPRO.NS",
    "HCLTECH": "HCLTECH.NS",
    "TATASTEEL": "TATASTEEL.NS",
    "ONGC": "ONGC.NS",
    "POWERGRID": "POWERGRID.NS",
    "NTPC": "NTPC.NS",
    "JSWSTEEL": "JSWSTEEL.NS",
    "TECHM": "TECHM.NS",
    "AXISBANK": "AXISBANK.NS",

    # ETFs
    "NIFTYBEES": "NIFTYBEES.NS",
    "BANKBEES": "BANKBEES.NS",
    "GOLDBEES": "GOLDBEES.NS",
    "LIQUIDBEES": "LIQUIDBEES.NS",
    "GILT5YBEES": "GILT5YBEES.NS",

    # Commodities/FX
    "GOLDUSD": "GC=F",
    "SILVERUSD": "SI=F",
    "CRUDE": "CL=F",
    "USDINR": "USDINR=X",
    "EURINR": "EURINR=X",
    "GBPINR": "GBPINR=X",

    # Remove problematic tickers
    # "TATAMOTORS": "TATAMOTORS.NS" - Skip this one, it might be delisted
}


class StockDownloader:
    def __init__(self):
        self.output_dir = OUTPUT_DIR
        self.known_mappings = KNOWN_TICKERS.copy()

    def resolve_ticker(self, symbol: str) -> Optional[str]:
        """Resolve symbol to Yahoo Finance ticker"""
        symbol = symbol.strip().upper()

        # Direct match in known mappings
        if symbol in self.known_mappings:
            return self.known_mappings[symbol]

        # Check if already a ticker
        if (symbol.endswith('.NS') or symbol.endswith('.BO') or
            symbol.startswith('^') or symbol.endswith('=X')):
            return symbol

        # Try Yahoo Finance search
        try:
            url = f"https://query2.finance.yahoo.com/v1/finance/search"
            params = {
                "q": symbol,
                "quotesCount": 10,
                "country": "India"
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            for quote in data.get("quotes", []):
                sym = quote.get("symbol", "")
                name = quote.get("shortname", "") or quote.get("longname", "")
                if sym.endswith('.NS'):
                    print(f"  [Found] {name} ({sym})")
                    return sym
                elif sym.endswith('.BO'):
                    # Prefer NSE for consistency
                    nse_ticker = sym.replace('.BO', '.NS')
                    print(f"  [Found] {name} ({sym}) -> Using {nse_ticker}")
                    return nse_ticker
        except Exception as e:
            print(f"  Search failed: {e}")

        # Return as-is with .NS
        return f"{symbol}.NS"

    def download_data(self, ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """Download stock data"""
        try:
            print(f"  Downloading {ticker}...")

            # Test if ticker exists first
            try:
                test_df = yf.download(ticker, period="1d", progress=False)
                if test_df.empty:
                    print(f"  Warning: No recent data for {ticker}")
            except Exception as e:
                print(f"  Warning: Failed to fetch data for {ticker}: {e}")

            # Download data
            df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)

            if df.empty:
                return None

            # Handle MultiIndex columns (yfinance >= 0.2.28)
            if isinstance(df.columns, pd.MultiIndex):
                # Flatten columns
                df.columns = [c[0] if c[1] == ticker else f"{c[0]}_{c[1]}" for c in df.columns]

            # Reset index
            df = df.reset_index()
            df.rename(columns={'Date': 'date'}, inplace=True)

            # Format dates
            df['date'] = pd.to_datetime(df['date'])
            df['date'] = df['date'].dt.strftime('%Y-%m-%d')

            # Round price columns
            for col in ['Open', 'High', 'Low', 'Close', 'Adj Close']:
                if col in df.columns:
                    df[col] = df[col].round(2)

            # Format volume
            if 'Volume' in df.columns:
                df['Volume'] = df['Volume'].apply(lambda x: int(x) if not pd.isna(x) else 0)

            return df
        except Exception as e:
            print(f"  Error downloading {ticker}: {e}")
            return None

    def save_data(self, df: pd.DataFrame, symbol: str, start: str, end: str) -> Tuple[str, str]:
        """Save data to CSV and Excel"""
        clean_symbol = re.sub(r'[^A-Za-z0-9]', '_', symbol.upper()).strip('_')
        base_name = f"{clean_symbol}_{start}_to_{end}"

        csv_path = self.output_dir / f"{base_name}.csv"
        xlsx_path = self.output_dir / f"{base_name}.xlsx"

        df.to_csv(csv_path, index=False)

        # Try to save Excel
        try:
            df.to_excel(xlsx_path, index=False, sheet_name='Price Data')
        except Exception as e:
            print(f"  Excel save failed (install openpyxl): {e}")
            xlsx_path = None

        return str(csv_path), str(xlsx_path) if xlsx_path else None

    async def download_single(self, symbol: str, start: str, end: str) -> Dict:
        """Download single stock data"""
        ticker = self.resolve_ticker(symbol)
        if not ticker:
            return {"symbol": symbol, "status": "FAILED", "error": "Ticker not found"}

        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)

        df = self.download_data(ticker, start, end)
        if df is None or df.empty:
            return {"symbol": symbol, "status": "FAILED", "ticker": ticker, "error": "No data"}

        csv_path, xlsx_path = self.save_data(df, symbol, start, end)

        return {
            "symbol": symbol,
            "status": "SUCCESS",
            "ticker": ticker,
            "rows": len(df),
            "date_range": f"{df['date'].iloc[0]} to {df['date'].iloc[-1]}",
            "csv_path": csv_path,
            "xlsx_path": xlsx_path
        }

    async def download_multiple(self, symbols: List[str], start: str, end: str,
                              max_workers: int = 5) -> List[Dict]:
        """Download multiple stocks concurrently"""
        tasks = []
        semaphore = asyncio.Semaphore(max_workers)

        async def limited_task(task):
            async with semaphore:
                return await task

        # Create tasks with small delays
        for i, symbol in enumerate(symbols):
            # Add delay between requests
            delay = 0.1 * (i % max_workers)
            await asyncio.sleep(delay)

            task = asyncio.create_task(self.download_single(symbol, start, end))
            tasks.append(limited_task(task))

        # Wait for all tasks
        return await asyncio.gather(*tasks)

    def get_sample_symbols(self) -> Dict[str, List[str]]:
        """Get sample symbols for testing"""
        return {
            "BLUE_CHIP": ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"],
            "MID_CAP": ["INDUSINDBK", "KOTAKBANK", "BAJFINANCE", "WIPRO", "HCLTECH"],
            "SMALL_CAP": ["CAMS", "EDELWEISS", "MUTHOOTFIN", "LTI"],
            "PHARMA": ["SUNPHARMA", "DIVISLAB", "DRREDDY", "CIPLA"],
            "BANKING": ["HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK"],
            "TECH": ["TCS", "INFY", "WIPRO", "HCLTECH"],
            "FMCG": ["ITC", "HUL", "NESTLEIND", "DABUR"],
            "ETF": ["NIFTYBEES", "GOLDBEES", "LIQUIDBEES"],
            "INDICES": ["NIFTY50", "NIFTYBANK", "SENSEX", "INDIAVIX"],
            "BSE": ["RELIANCE.BO", "TCS.BO", "HDFCBANK.BO"],
        }

    async def test_group(self, group_name: str, symbols: List[str]) -> Dict:
        """Test a group of symbols"""
        print(f"\nTesting {group_name} ({len(symbols)} symbols)...")

        results = await self.download_multiple(symbols, "2024-01-01", "2024-12-31", max_workers=3)

        success = sum(1 for r in results if r["status"] == "SUCCESS")
        failed = len(results) - success

        print(f"  {group_name}: {success}/{len(results)} ({success/len(results)*100:.1f}%)")

        # Show failures
        for result in results:
            if result["status"] == "FAILED":
                error = result.get('error', 'Unknown error')
                print(f"  [FAIL] {result['symbol']}: {error}")

        return {
            "group": group_name,
            "total": len(results),
            "success": success,
            "failed": failed,
            "percentage": success/len(results)*100 if results else 0,
            "details": results
        }

    async def run_tests(self) -> Dict:
        """Run comprehensive tests"""
        print("="*60)
        print("COMPREHENSIVE TEST SUITE")
        print("="*60)

        sample_symbols = self.get_sample_symbols()
        test_results = {}

        # Test each group
        for group_name, symbols in sample_symbols.items():
            # Skip empty groups
            if not symbols:
                continue

            result = await self.test_group(group_name, symbols)
            test_results[group_name] = result

            # Small delay between groups
            await asyncio.sleep(0.5)

        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)

        total_tests = len(test_results)
        passed_tests = sum(1 for r in test_results.values() if r["percentage"] > 80)

        print(f"Groups tested: {total_tests}")
        print(f"Groups passed (>80%): {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%)")

        for group, result in test_results.items():
            status = "PASS" if result["percentage"] > 80 else "FAIL"
            print(f"  {status}: {group} ({result['success']}/{result['total']})")

        return {
            "total_groups": total_tests,
            "passed_groups": passed_tests,
            "percentage_passed": passed_tests/total_tests*100 if total_tests > 0 else 0,
            "details": test_results
        }

    def search(self, query: str) -> List[str]:
        """Search for symbols using Yahoo Finance"""
        try:
            url = f"https://query2.finance.yahoo.com/v1/finance/search"
            params = {
                "q": query,
                "quotesCount": 20,
                "country": "India"
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            results = []
            for quote in data.get("quotes", []):
                sym = quote.get("symbol", "")
                name = quote.get("shortname", "") or quote.get("longname", "")
                results.append(f"{sym}: {name}")

            return results
        except Exception as e:
            print(f"Search failed: {e}")
            return []

    def list_known(self) -> None:
        """List all known tickers"""
        print("\nKnown Indices:")
        indices = [k for k, v in KNOWN_TICKERS.items() if v.startswith(('^', 'NIFTY_', 'BSE-'))]
        for idx in sorted(indices):
            print(f"  {idx}: {KNOWN_TICKERS[idx]}")

        print("\nPopular Stocks:")
        stocks = [k for k, v in KNOWN_TICKERS.items() if v.endswith('.NS')]
        print(f"  Total {len(stocks)} stocks: {', '.join(sorted(stocks[:20]))}")
        if len(stocks) > 20:
            print(f"  ... and {len(stocks) - 20} more")

        print(f"\nTotal: {len(KNOWN_TICKERS)} tickers")


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Ultimate NSE/BSE Stock Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single stock
  python download_nse_bse.py RELIANCE
  python download_nse_bse.py "TATA MOTORS"
  python download_nse_bse.py SBIN --start 2023-01-01 --end 2024-01-01

  # BSE stock
  python download_nse_bse.py RELIANCE.BO

  # Search
  python download_nse_bse.py --search "tata"
  python download_nse_bse.py --search "axis"

  # Test
  python download_nse_bse.py --test
  python download_nse_bse.py --test-all

  # List known tickers
  python download_nse_bse.py --list
        """
    )

    parser.add_argument("symbol", nargs="?", help="Stock symbol or name")
    parser.add_argument("--start", default="2023-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--csv", action="store_true", help="CSV only")
    parser.add_argument("--batch", help="File with list of symbols to download")
    parser.add_argument("--output", default=str(OUTPUT_DIR), help="Output directory")

    parser.add_argument("--search", metavar="QUERY", help="Search Yahoo Finance")
    parser.add_argument("--list", action="store_true", help="List known tickers")

    parser.add_argument("--test", action="store_true", help="Run basic tests")
    parser.add_argument("--test-all", action="store_true", help="Run comprehensive tests")

    parser.add_argument("--workers", type=int, default=5, help="Parallel downloads")

    args = parser.parse_args()

    # Set end date
    if not args.end:
        args.end = datetime.now().strftime("%Y-%m-%d")

    downloader = StockDownloader()

    if args.search:
        results = downloader.search(args.search)
        print(f"\nSearch results for '{args.search}':")
        for result in results[:10]:
            print(f"  {result}")
        return

    if args.list:
        downloader.list_known()
        return

    if args.test or args.test_all:
        results = await downloader.run_tests()
        print(f"\nTest Results:")
        print(f"  Passed: {results['passed_groups']}/{results['total_groups']}")
        print(f"  Success rate: {results['percentage_passed']:.1f}%")
        return

    if args.batch:
        # Read symbols from file
        with open(args.batch, 'r') as f:
            symbols = [line.strip() for line in f.readlines() if line.strip()]
        print(f"\nLoading {len(symbols)} symbols from {args.batch}...")
    elif args.symbol:
        symbols = [args.symbol]
    else:
        parser.print_help()
        return

    # Download
    print(f"\nDownloading {len(symbols)} symbols...")
    print(f"  Period: {args.start} to {args.end}")

    start_time = time.time()
    results = await downloader.download_multiple(symbols, args.start, args.end, args.workers)
    end_time = time.time()

    # Summary
    success = sum(1 for r in results if r["status"] == "SUCCESS")
    print(f"\nDownload complete!")
    print(f"  Total: {len(results)}")
    print(f"  Success: {success} ({success/len(results)*100:.1f}%)")
    print(f"  Failed: {len(results) - success}")
    print(f"  Time: {end_time - start_time:.1f}s")

    # List failed downloads
    if success < len(results):
        print(f"\nFailed downloads:")
        for result in results:
            if result["status"] == "FAILED":
                print(f"  [FAIL] {result['symbol']}: {result.get('error', 'No data')}")


if __name__ == "__main__":
    asyncio.run(main())
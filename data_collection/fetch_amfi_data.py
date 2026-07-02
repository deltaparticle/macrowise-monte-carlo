#!/usr/bin/env python3
"""
AMFI Mutual Fund NAV Data Fetcher
=================================
Collects historical NAV data for Indian mutual funds from AMFI India.
AMFI publishes daily NAV for all registered mutual fund schemes.

Data Source: https://www.amfiindia.com/spages/NAVHistoryReport.aspx

Scheme Code Reference:
- Equity funds: 100000 series
- Debt funds: 200000 series
- Hybrid funds: 300000 series
- Solution-oriented: 400000 series
- Other: 500000+ series

The NAVHistoryReport.aspx accepts parameters:
  ?mf=<scheme-code>&frmdt=<DD-MM-YYYY>&todt=<DD-MM-YYYY>
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from io import StringIO

import pandas as pd
import requests

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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/csv, */*",
    "Referer": "https://www.amfiindia.com/",
}

# =============================================================================
# MUTUAL FUND SCHEME CODES (Direct Growth Plans)
# =============================================================================

EQUITY_SCHEMES = {
    # Large Cap Equity
    "LargeCap_Equity": {
        "Axis_Bluechip_DirectG": "119275",
        "Mirae_Largecap_DirectG": "118525",
        "UTI_Nifty50_DirectG": "148524",
        "HDFC_Top100_DirectG": "119034",
    },
    # Large & Mid Cap
    "LargeMidCap_Equity": {
        "Canara_Robeco_Bluechip_DirectG": "119106",
        "Kotak_Bluechip_DirectG": "119109",
        "Mirae_LargeMid_DirectG": "118552",
    },
    # Mid Cap
    "MidCap_Equity": {
        "Kotak_EmergingEquity_DirectG": "119355",
        "HDFC_Midcap_DirectG": "119194",
        "Quant_Midcap_DirectG": "120842",
        "Nippon_Growth_DirectG": "119266",
    },
    # Small Cap
    "SmallCap_Equity": {
        "SBI_SmallCap_DirectG": "119218",
        "HDFC_Smallcap_DirectG": "119206",
        "Nippon_SmallCap_DirectG": "119234",
        "Quant_SmallCap_DirectG": "120836",
    },
    # Multi Cap / Flexi Cap
    "MultiCap_Equity": {
        "Parag_Parikh_FlexiCap_DirectG": "119423",
        "Quant_FlexiCap_DirectG": "149216",
        "Mirae_FlexiCap_DirectG": "148943",
        "HDFC_FlexiCap_DirectG": "149028",
    },
    # ELSS
    "ELSS": {
        "Mirae_TaxSaver_DirectG": "119520",
        "Kotak_TaxSaver_DirectG": "119369",
        "SBI_LongTermEquity_DirectG": "119220",
        "Quant_TaxPlan_DirectG": "120828",
    },
    # Sectoral - IT
    "Sectoral_IT": {
        "Tata_DigitalIndia_DirectG": "149004",
    },
    # Sectoral - Pharma
    "Sectoral_Pharma": {
        "SBI_Pharma_DirectG": "119267",
        "Nippon_Pharma_DirectG": "119643",
    },
    # Value / Thematic
    "Value_Equity": {
        "Tata_Value_DirectG": "120654",
    },
    # Index Funds
    "Index_Funds": {
        "UTI_Nifty50_DirectG": "148524",
        "UTI_NiftyNext50_DirectG": "148522",
        "UTI_Nifty100_DirectG": "148523",
        "UTI_Nifty200_DirectG": "150987",
        "HDFC_Nifty50_DirectG": "149197",
        "SBI_Nifty50_DirectG": "149019",
        "ICICI_Nifty50_DirectG": "149237",
        "UTI_NiftyMidcap100_DirectG": "150989",
        "UTI_NiftySmallcap100_DirectG": "150991",
    },
}

DEBT_SCHEMES = {
    # Liquid
    "Liquid_Funds": {
        "Nippon_Liquid_DirectG": "119553",
        "ICICI_Liquid_DirectG": "119594",
        "HDFC_Liquid_DirectG": "119248",
        "SBI_Liquid_DirectG": "119391",
        "Aditya_Liquid_DirectG": "119687",
    },
    # Ultra Short Duration
    "UltraShort_Funds": {
        "Franklin_UltraShort_DirectG": "119269",
        "ICICI_UltraShort_DirectG": "119589",
        "HDFC_UltraShort_DirectG": "119198",
    },
    # Low Duration
    "LowDuration_Funds": {
        "ICICI_LowDuration_DirectG": "119731",
        "HDFC_LowDuration_DirectG": "149277",
    },
    # Corporate Bond
    "Corporate_Bond": {
        "ICICI_CorpBond_DirectG": "119524",
        "Kotak_CorpBond_DirectG": "119301",
        "Aditya_CorpBond_DirectG": "119613",
    },
    # Dynamic Bond
    "Dynamic_Bond": {
        "ICICI_DynamicBond_DirectG": "119388",
        "HDFC_DynamicBond_DirectG": "119341",
    },
    # Gilt Funds
    "Gilt_Funds": {
        "SBI_Gilt_DirectG": "119597",
        "ICICI_Gilt_DirectG": "119311",
        "HDFC_Gilt_DirectG": "119348",
    },
    # Banking & PSU
    "Banking_PSU": {
        "ICICI_BankingPSU_DirectG": "149004",
    },
    # Short Duration
    "ShortDuration_Funds": {
        "ICICI_ShortDuration_DirectG": "119388",
    },
}

HYBRID_SCHEMES = {
    # Aggressive Hybrid (Equity oriented)
    "Aggressive_Hybrid": {
        "ICICI_PrudEquityDebt_DirectG": "119261",
        "HDFC_HybridEquity_DirectG": "119198",
        "SBI_HybridEquity_DirectG": "119464",
        "Kotak_HybridEquity_DirectG": "119369",
    },
    # Conservative Hybrid
    "Conservative_Hybrid": {
        "ICICI_PrudHybrid_DirectG": "119582",
        "HDFC_HybridDebt_DirectG": "119351",
    },
    # Balanced Advantage
    "BalancedAdvantage": {
        "ICICI_BalancedAdvantage_DirectG": "119588",
        "HDFC_BalancedAdvantage_DirectG": "119378",
    },
    # Arbitrage
    "Arbitrage": {
        "Kotak_Arbitrage_DirectG": "119417",
        "ICICI_Arbitrage_DirectG": "119670",
    },
}

GOLD_ETF_SCHEMES = {
    "Gold_ETF": {
        "Nippon_Gold_Bees_DirectG": "119509",
        "SBI_Gold_ETF_DirectG": "119728",
        "ICICI_PrudGold_Bees_DirectG": "119637",
    },
}

SOLUTION_SCHEMES = {
    # Retirement
    "Retirement_Funds": {
        "HDFC_Retirement_DirectG": "120297",
        "ICICI_PrudRetirement_DirectG": "119642",
    },
    # Children
    "Children_Funds": {
        "SBI_ChildrensBenefit_DirectG": "119465",
    },
}


def fetch_nav_history(scheme_code: str, start_date: str, end_date: str) -> pd.Series:
    """Fetch historical NAV for a single scheme code."""
    session = requests.Session()
    session.headers.update(HEADERS)

    params = {
        "mf": scheme_code,
        "frmdt": start_date,
        "todt": end_date,
    }

    try:
        resp = session.get(
            "https://www.amfiindia.com/spages/NAVHistoryReport.aspx",
            params=params,
            timeout=30,
        )

        if resp.status_code == 200:
            df = pd.read_csv(
                StringIO(resp.text),
                skiprows=1,
                names=["Date", "NAV", "Repurchase_Price", "Sale_Price"],
            )
            df["Date"] = pd.to_datetime(df["Date"], format="%d-%b-%Y", errors="coerce")
            df["NAV"] = pd.to_numeric(df["NAV"], errors="coerce")
            df = df.dropna(subset=["NAV"]).sort_values("Date")
            series = df.set_index("Date")["NAV"]
            series.name = scheme_code
            return series
        return pd.Series(dtype=float, name=scheme_code)
    except Exception as e:
        return pd.Series(dtype=float, name=scheme_code)


def collect_amfi_schemes(
    schemes: dict,
    start_date: str = "01-Jan-2015",
    end_date: str = None,
) -> dict:
    """
    Collect NAV history for a batch of AMFI schemes.

    Args:
        schemes: dict of {category: {scheme_name: scheme_code, ...}, ...}
        start_date: DD-Mon-YYYY format
        end_date: DD-Mon-YYYY format (default: today)
    """
    if end_date is None:
        end_date = datetime.now().strftime("%d-%b-%Y")

    results = {}

    for category, scheme_dict in schemes.items():
        print(f"  [{category}]...")
        cat_data = {}

        for name, code in scheme_dict.items():
            print(f"    {name} ({code})...", end=" ", flush=True)
            series = fetch_nav_history(code, start_date, end_date)

            if not series.empty:
                print(f"OK ({len(series)} records)")
            else:
                print("EMPTY")

            cat_data[name] = series
            time.sleep(0.5)

        # Combine category
        if cat_data:
            combined = pd.DataFrame(cat_data)
            results[category] = combined

    return results


def collect_all_amfi_data(
    start_date: str = "01-Jan-2015",
    end_date: str = None,
) -> dict:
    """
    Collect NAV data for ALL Indian mutual fund categories.
    Saves to data/amfi/
    """
    if end_date is None:
        end_date = datetime.now().strftime("%d-%b-%Y")

    print(f"\n[AMFI] Collecting all mutual fund NAV data ({start_date} to {end_date})...")

    all_results = {}

    # Equity
    print("\n[Equity Funds]")
    eq = collect_amfi_schemes(EQUITY_SCHEMES, start_date, end_date)
    if eq:
        all_results["equity"] = eq

    # Debt
    print("\n[Debt Funds]")
    debt = collect_amfi_schemes(DEBT_SCHEMES, start_date, end_date)
    if debt:
        all_results["debt"] = debt

    # Hybrid
    print("\n[Hybrid Funds]")
    hy = collect_amfi_schemes(HYBRID_SCHEMES, start_date, end_date)
    if hy:
        all_results["hybrid"] = hy

    # Gold
    print("\n[Gold ETFs]")
    gold = collect_amfi_schemes(GOLD_ETF_SCHEMES, start_date, end_date)
    if gold:
        all_results["gold_etf"] = gold

    # Solution-oriented
    print("\n[Solution-Oriented Funds]")
    sol = collect_amfi_schemes(SOLUTION_SCHEMES, start_date, end_date)
    if sol:
        all_results["solution"] = sol

    # Save
    if all_results:
        amfi_dir = PROCESSED_DIR / "amfi"
        amfi_dir.mkdir(parents=True, exist_ok=True)

        # Save each category
        for category, cat_data in all_results.items():
            for name, df in cat_data.items():
                if not df.empty:
                    out_path = amfi_dir / f"{category}_{name}.csv"
                    df.to_csv(out_path)
                    print(f"  Saved: {out_path}")

        # Save combined NAV dataset
        all_dfs = []
        for cat_data in all_results.values():
            for df in cat_data.values():
                if not df.empty and isinstance(df, pd.DataFrame):
                    all_dfs.append(df)

        if all_dfs:
            # Combine all columns
            combined = pd.concat(all_dfs, axis=1)
            combined.index.name = "date"
            combined.index = pd.to_datetime(combined.index)

            # Add suffix for overlapping columns
            combined.columns = [f"{col}" if col not in combined.columns[:i] else f"{col}_{i}"
                                for i, col in enumerate(combined.columns)]

            save_dataframe(combined, "amfi_all_nav")

    return all_results


def generate_amfi_scheme_list() -> dict:
    """
    Fetch the AMFI scheme master list to get all scheme codes.
    Returns: dict of scheme_code -> scheme details
    """
    print("\n[AMFI] Fetching scheme master list...")

    try:
        resp = requests.get(
            "https://www.amfiindia.com/spages/NAVAllReport.aspx",
            headers=HEADERS,
            timeout=30,
        )
        if resp.status_code == 200:
            df = pd.read_csv(StringIO(resp.text), skiprows=1, on_bad_lines="skip")
            print(f"  Found {len(df)} schemes")
            df.columns = [str(c).strip() for c in df.columns]
            save_dataframe(df, "amfi_scheme_master", processed=False)
            return df.to_dict()
    except Exception as e:
        print(f"  Error: {e}")

    return {}


def collect_amfi_monthly_returns() -> dict:
    """
    Collect all NAV data and compute monthly returns.
    """
    print("\n[AMFI] Computing monthly returns...")

    amfi_dir = PROCESSED_DIR / "amfi"
    if not amfi_dir.exists():
        print("  No AMFI data found. Run collect_all_amfi_data first.")
        return {}

    monthly_results = {}

    for csv_file in sorted(amfi_dir.glob("*.csv")):
        print(f"  Processing {csv_file.stem}...", end=" ", flush=True)
        df = pd.read_csv(csv_file, index_col=0, parse_dates=True)
        df.index.name = "date"

        if df.empty:
            print("empty")
            continue

        # Compute monthly returns from daily NAV
        monthly = df.resample("ME").last()
        monthly_ret = monthly.pct_change()

        monthly_results[csv_file.stem] = monthly_ret
        print(f"OK ({len(monthly_ret)} months, {monthly_ret.columns.tolist()})")

    return monthly_results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="01-Jan-2015")
    parser.add_argument("--end", default=None)
    parser.add_argument("--list-schemes", action="store_true")
    parser.add_argument("--equity", action="store_true")
    parser.add_argument("--debt", action="store_true")
    parser.add_argument("--hybrid", action="store_true")
    parser.add_argument("--returns", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.end is None:
        args.end = datetime.now().strftime("%d-%b-%Y")

    if args.all or args.list_schemes:
        generate_amfi_scheme_list()

    if args.all or args.returns:
        collect_amfi_monthly_returns()
    else:
        if args.all or args.equity:
            collect_amfi_schemes(EQUITY_SCHEMES, args.start, args.end)
        if args.all or args.debt:
            collect_amfi_schemes(DEBT_SCHEMES, args.start, args.end)
        if args.all or args.hybrid:
            collect_amfi_schemes(HYBRID_SCHEMES, args.start, args.end)

        if args.all or not (args.equity or args.debt or args.hybrid or args.returns or args.list_schemes):
            collect_all_amfi_data(args.start, args.end)

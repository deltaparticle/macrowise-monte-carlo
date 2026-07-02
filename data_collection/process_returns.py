
#!/usr/bin/env python3
"""
Indian Equity Index Monthly Returns Generator
=============================================
Processes collected daily data into the exact format PortfolioVisualizer uses:
- Monthly total return series for each asset class
- Annual return statistics (mean, std, correlation matrix)
- Inflation-adjusted returns

This is the processing pipeline that takes raw daily data and produces
the clean monthly return matrix used for Monte Carlo simulation.

Output files:
  data/processed/indian_monthly_returns.csv
  data/processed/indian_annual_returns.csv
  data/processed/indian_asset_statistics.csv
  data/processed/indian_correlation_matrix.csv
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

# =============================================================================
# CONFIG
# =============================================================================
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

for d in [DATA_DIR, RAW_DIR, PROCESSED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# =============================================================================
# ASSET CLASS DEFINITIONS (India)
# =============================================================================

# The 11 core asset classes for Indian Monte Carlo
# Mirrors PortfolioVisualizer's asset class structure but for Indian markets
INDIAN_ASSET_CLASSES = {
    # Equity - Broad Market
    "IN_EQ_NIFTY50": {
        "name": "Nifty 50 Index",
        "source": "NSE",
        "category": "Indian Equity - Large Cap",
        "description": "NSE Nifty 50 - 50 large-cap Indian stocks",
    },
    "IN_EQ_NIFTY100": {
        "name": "Nifty 100 Index",
        "source": "NSE",
        "category": "Indian Equity - Large Cap",
        "description": "NSE Nifty 100 - 100 large/mid-cap Indian stocks",
    },
    "IN_EQ_NIFTY200": {
        "name": "Nifty 200 Index",
        "source": "NSE",
        "category": "Indian Equity - Broad Market",
        "description": "NSE Nifty 200 - 200 large/mid-cap Indian stocks",
    },
    "IN_EQ_NIFTY500": {
        "name": "Nifty 500 Index",
        "source": "NSE",
        "category": "Indian Equity - Broad Market",
        "description": "NSE Nifty 500 - 500 Indian stocks covering ~96% market cap",
    },
    # Market Cap Segments
    "IN_EQ_MIDCAP100": {
        "name": "Nifty Midcap 100",
        "source": "NSE",
        "category": "Indian Equity - Mid Cap",
        "description": "NSE Nifty Midcap 100 Index",
    },
    "IN_EQ_SMALLCAP100": {
        "name": "Nifty Smallcap 100",
        "source": "NSE",
        "category": "Indian Equity - Small Cap",
        "description": "NSE Nifty Smallcap 100 Index",
    },
    # Sectoral
    "IN_EQ_BANK": {
        "name": "Nifty Bank Index",
        "source": "NSE",
        "category": "Indian Equity - Sectoral",
        "description": "NSE Nifty Bank Index - Banking & financial stocks",
    },
    "IN_EQ_IT": {
        "name": "Nifty IT Index",
        "source": "NSE",
        "category": "Indian Equity - Sectoral",
        "description": "NSE Nifty IT Index - IT services companies",
    },
    "IN_EQ_PHARMA": {
        "name": "Nifty Pharma Index",
        "source": "NSE",
        "category": "Indian Equity - Sectoral",
        "description": "NSE Nifty Pharma Index",
    },
    "IN_EQ_FMCG": {
        "name": "Nifty FMCG Index",
        "source": "NSE",
        "category": "Indian Equity - Sectoral",
        "description": "NSE Nifty FMCG Index",
    },
    "IN_EQ_AUTO": {
        "name": "Nifty Auto Index",
        "source": "NSE",
        "category": "Indian Equity - Sectoral",
        "description": "NSE Nifty Auto Index",
    },
    "IN_EQ_REALTY": {
        "name": "Nifty Realty Index",
        "source": "NSE",
        "category": "Indian Equity - Sectoral",
        "description": "NSE Nifty Realty Index",
    },
    "IN_EQ_METAL": {
        "name": "Nifty Metal Index",
        "source": "NSE",
        "category": "Indian Equity - Sectoral",
        "description": "NSE Nifty Metal Index",
    },
    # Bonds / Fixed Income
    "IN_BOND_10Y": {
        "name": "Nifty 10Y G-Sec Index",
        "source": "NSE",
        "category": "Indian Bonds - G-Sec",
        "description": "10-year Government Securities Index",
    },
    "IN_BOND_10Y_TBILL": {
        "name": "91D T-Bill",
        "source": "RBI",
        "category": "Indian Bonds - T-Bill",
        "description": "91-day Treasury Bill rate (risk-free proxy)",
    },
    "IN_BOND_CORP": {
        "name": "Nifty Corporate Bond Index",
        "source": "NSE",
        "category": "Indian Bonds - Corporate",
        "description": "Nifty Corporate Bond Index",
    },
    "IN_BOND_LIQUID": {
        "name": "Nifty 1D Liquid Index",
        "source": "NSE",
        "category": "Indian Bonds - Liquid",
        "description": "Overnight liquid fund equivalent",
    },
    "IN_BOND_GILT": {
        "name": "Nifty G-Sec Long Term",
        "source": "NSE",
        "category": "Indian Bonds - G-Sec",
        "description": "Nifty Long Term Government Securities",
    },
    # Gold
    "IN_GOLD": {
        "name": "Gold Price (INR)",
        "source": "MCX/RBI",
        "category": "Commodities - India",
        "description": "Gold price in INR per 10 grams",
    },
    # Silver
    "IN_SILVER": {
        "name": "Silver Price (INR)",
        "source": "MCX",
        "category": "Commodities - India",
        "description": "Silver price in INR per kg",
    },
    # Cash / Risk Free
    "IN_CASH": {
        "name": "Indian Cash / Overnight Rate",
        "source": "RBI",
        "category": "Indian Bonds - Cash",
        "description": "Repo rate proxy for risk-free rate",
    },
    # India Inflation
    "IN_INFLATION": {
        "name": "India CPI Combined",
        "source": "MOSPI",
        "category": "India Macro",
        "description": "CPI Combined (Base 2012=100) year-on-year change",
    },
    # International - for diversification
    "GLOBAL_US_EQ": {
        "name": "US Total Stock Market",
        "source": "CRSP/Yahoo",
        "category": "Global Equity",
        "description": "US Total Stock Market (VTI proxy)",
    },
    "GLOBAL_BONDS": {
        "name": "Global Bonds",
        "source": "Bloomberg/Yahoo",
        "category": "Global Bonds",
        "description": "Global aggregate bonds (AGG proxy)",
    },
}


# =============================================================================
# FUNCTIONS
# =============================================================================


def load_data_file(filename: str, directory: str = "processed") -> pd.DataFrame:
    """Load a data file (CSV or pickle)."""
    csv_path = DATA_DIR / directory / f"{filename}.csv"
    pkl_path = DATA_DIR / directory / f"{filename}.pkl"

    if pkl_path.exists():
        return pd.read_pickle(pkl_path)
    elif csv_path.exists():
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        df.index.name = "date"
        return df
    else:
        return pd.DataFrame()


def compute_monthly_returns_from_daily(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert daily closing prices to monthly returns.
    Uses month-end prices for return calculation.
    """
    if daily_df.empty:
        return pd.DataFrame()

    # Ensure numeric
    daily_df = daily_df.apply(pd.to_numeric, errors="coerce")

    # Resample to month-end (last day of each month)
    monthly_prices = daily_df.resample("ME").last()

    # Compute monthly returns
    monthly_returns = monthly_prices.pct_change()

    # Drop first row (NaN from pct_change)
    monthly_returns = monthly_returns.iloc[1:]

    return monthly_returns


def compute_annual_returns_from_monthly(monthly_returns: pd.DataFrame) -> pd.DataFrame:
    """
    Convert monthly returns to annual returns.
    """
    if monthly_returns.empty:
        return pd.DataFrame()

    # Annualize using compound return: (1 + r1) * (1 + r2) * ... - 1
    annual_returns = (1 + monthly_returns).resample("YE").prod() - 1
    return annual_returns


def compute_asset_statistics(monthly_returns: pd.DataFrame) -> pd.DataFrame:
    """
    Compute key statistics for each asset class.

    Returns DataFrame with columns:
    - mean_annual: Annualized mean return
    - std_annual: Annualized volatility
    - geo_mean_annual: Geometric mean annual return
    - sharpe_ratio: Sharpe ratio (using repo rate as risk-free)
    - max_drawdown: Maximum drawdown
    - skewness: Return distribution skewness
    - kurtosis: Return distribution kurtosis
    - n_months: Number of monthly observations
    - start_date / end_date: Data range
    """
    if monthly_returns.empty:
        return pd.DataFrame()

    stats = {}

    for col in monthly_returns.columns:
        series = monthly_returns[col].dropna()
        if len(series) < 24:
            continue

        mean_m = series.mean()
        std_m = series.std()
        mean_a = (1 + mean_m) ** 12 - 1
        std_a = std_m * np.sqrt(12)

        # Geometric mean
        cum_ret = (1 + series).prod()
        n_yrs = len(series) / 12
        geo_mean_a = cum_ret ** (1 / n_yrs) - 1 if n_yrs > 0 else 0

        # Sharpe ratio (risk-free = 6.5% India repo rate avg)
        sharpe = (mean_a - 0.065) / std_a if std_a > 0 else 0

        # Max Drawdown
        cum = (1 + series).cumprod()
        peak = cum.expanding().max()
        dd = (cum - peak) / peak
        max_dd = dd.min()

        # Value at Risk (95%)
        var_95 = series.quantile(0.05)

        # Conditional Value at Risk
        cvar_95 = series[series <= var_95].mean()

        # Best / Worst month
        best_month = series.max()
        worst_month = series.min()

        # Best / Worst year
        annual = compute_annual_returns_from_monthly(series.to_frame())
        best_year = annual.iloc[:, 0].max() if not annual.empty else np.nan
        worst_year = annual.iloc[:, 0].min() if not annual.empty else np.nan

        stats[col] = {
            "mean_monthly": mean_m,
            "std_monthly": std_m,
            "mean_annual": mean_a,
            "std_annual": std_a,
            "geo_mean_annual": geo_mean_a,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "var_95_monthly": var_95,
            "cvar_95_monthly": cvar_95,
            "skewness": series.skew(),
            "kurtosis": series.kurtosis(),
            "best_month": best_month,
            "worst_month": worst_month,
            "best_year": best_year,
            "worst_year": worst_year,
            "n_months": len(series),
            "n_years": n_yrs,
            "start_date": series.index[0].strftime("%Y-%m-%d"),
            "end_date": series.index[-1].strftime("%Y-%m-%d"),
        }

    df = pd.DataFrame(stats).T
    df.index.name = "asset"

    # Reorder columns
    col_order = [
        "mean_annual", "std_annual", "geo_mean_annual", "sharpe_ratio",
        "max_drawdown", "var_95_monthly", "cvar_95_monthly",
        "skewness", "kurtosis",
        "best_month", "worst_month", "best_year", "worst_year",
        "n_months", "n_years", "start_date", "end_date",
    ]
    df = df[[c for c in col_order if c in df.columns]]

    return df


def compute_correlation_matrix(monthly_returns: pd.DataFrame) -> pd.DataFrame:
    """
    Compute correlation matrix for all monthly return series.
    """
    if monthly_returns.empty:
        return pd.DataFrame()

    return monthly_returns.corr()


def compute_covariance_matrix(monthly_returns: pd.DataFrame) -> pd.DataFrame:
    """
    Compute covariance matrix (annualized) for all monthly return series.
    """
    if monthly_returns.empty:
        return pd.DataFrame()

    cov_monthly = monthly_returns.cov()
    cov_annual = cov_monthly * 12
    return cov_annual


def generate_summary_report() -> str:
    """
    Generate a comprehensive summary report of the data pipeline.
    """
    report = []
    report.append("=" * 70)
    report.append("  INDIAN MONTE CARLO SIMULATOR - DATA SUMMARY REPORT")
    report.append("=" * 70)
    report.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")

    # Asset Statistics
    stats = load_data_file("indian_asset_statistics")
    if not stats.empty:
        report.append(f"[ Asset Statistics ]")
        report.append(f"  Assets covered: {len(stats)}")
        report.append("")
        for asset, row in stats.iterrows():
            report.append(f"  {asset}:")
            report.append(f"    Mean Return (Annual):  {row.get('mean_annual', 0):.2%}")
            report.append(f"    Volatility (Annual):   {row.get('std_annual', 0):.2%}")
            report.append(f"    Sharpe Ratio:          {row.get('sharpe_ratio', 0):.2f}")
            report.append(f"    Max Drawdown:          {row.get('max_drawdown', 0):.2%}")
            report.append(f"    Skewness:              {row.get('skewness', 0):.2f}")
            report.append(f"    Kurtosis:              {row.get('kurtosis', 0):.2f}")
            report.append(f"    Data Range:            {row.get('start_date', 'N/A')} to {row.get('end_date', 'N/A')}")
            report.append("")

    # Correlation Matrix
    corr = load_data_file("indian_correlation_matrix")
    if not corr.empty:
        report.append(f"[ Correlation Matrix ]")
        report.append(f"  Assets: {len(corr)}")
        report.append("")

    report.append("=" * 70)

    return "\n".join(report)


def save_config_summary() -> dict:
    """
    Save a JSON configuration summary of all data pipeline settings
    and available asset classes.
    """
    config = {
        "version": "1.0",
        "created": datetime.now().isoformat(),
        "description": "Indian Monte Carlo Simulator - Data Configuration",
        "asset_classes": INDIAN_ASSET_CLASSES,
        "data_sources": {
            "NSE": {
                "url": "https://www.nseindia.com/api/historical/indices/historical",
                "indices": "Nifty 50, 100, 200, 500, sectoral indices, G-Sec indices",
            },
            "RBI": {
                "url": "https://www.rbi.org.in",
                "wss": "https://www.rbi.org.in/Scripts/WS_SectionIndex.aspx",
                "tables": "H1-H19 (Policy rates, T-Bill, CPI, FX, Gold/Silver)",
            },
            "AMFI": {
                "url": "https://www.amfiindia.com/spages/NAVHistoryReport.aspx",
                "nav_data": "Daily NAV for all Indian mutual fund schemes",
            },
            "MOSPI": {
                "url": "https://www.mospi.gov.in/",
                "cpi": "Consumer Price Index (combined, rural, urban)",
            },
            "MCX": {
                "url": "https://www.mcxindia.com/",
                "commodities": "Gold, Silver, Crude Oil prices",
            },
        },
        "simulation_parameters": {
            "currency": "INR",
            "risk_free_rate_default": 0.065,
            "inflation_data": "CPI Combined India (base 2012=100)",
            "rebalancing_default": "Annual",
            "monthly_returns_used": True,
            "correlation_handling": "Cholesky decomposition",
        },
        "tax_rules_file": "data/tax_rules_india.json",
        "life_expectancy_file": "data/life_expectancy_india.csv",
    }

    config_path = DATA_DIR / "config_summary.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, default=str)

    print(f"  Saved config summary to {config_path}")
    return config


# =============================================================================
# MAIN
# =============================================================================


def process_all_data():
    """Process all collected raw data into the final simulation-ready format."""
    print("=" * 60)
    print("  PROCESSING INDIAN MARKET DATA")
    print("=" * 60)

    # 1. Load NSE Equity Indices
    print("\n[1] Loading NSE Equity Indices...")
    eq_data = load_data_file("nse_equity_indices")
    eq_alt = load_data_file("nse_equity_indices_alt")

    if eq_data.empty and eq_alt.empty:
        print("  WARNING: No NSE equity data found. Run fetch_nse_data.py first.")
    else:
        source = eq_data if not eq_data.empty else eq_alt
        print(f"  Loaded {len(source)} rows, {len(source.columns)} indices")

    # 2. Load Bond Data
    print("\n[2] Loading Bond Data...")
    bond_data = load_data_file("nse_gsec_indices")
    bond_data_raw = load_data_file("nse_bond_indices")

    if not bond_data.empty:
        print(f"  G-Sec indices: {len(bond_data)} rows")
    elif not bond_data_raw.empty:
        print(f"  Bond indices: {len(bond_data_raw)} rows")
    else:
        print("  WARNING: No bond data found.")

    # 3. Load CPI
    print("\n[3] Loading CPI Data...")
    cpi = load_data_file("cpi_inflation")
    cpi_data = load_data_file("cpi_data")

    cpi_source = cpi if not cpi.empty else cpi_data
    if not cpi_source.empty:
        print(f"  CPI: {len(cpi_source)} rows")
    else:
        print("  WARNING: No CPI data found.")

    # 4. Compute Monthly Returns
    print("\n[4] Computing Monthly Returns...")

    all_data = {}
    if not eq_data.empty:
        all_data["equity"] = eq_data
    if not eq_alt.empty:
        all_data["equity_alt"] = eq_alt
    if not bond_data.empty:
        all_data["bonds"] = bond_data
    if not bond_data_raw.empty:
        all_data["bonds_raw"] = bond_data_raw

    monthly_returns = {}
    annual_returns = {}

    for name, df in all_data.items():
        if not df.empty:
            monthly = compute_monthly_returns_from_daily(df)
            if not monthly.empty:
                monthly_returns[name] = monthly
                annual = compute_annual_returns_from_monthly(monthly)
                annual_returns[name] = annual
                print(f"  {name}: {len(monthly)} months, {len(annual)} years")

    # Combine all monthly returns
    if monthly_returns:
        combined_monthly = pd.concat(monthly_returns.values(), axis=1)
        combined_monthly.columns = [
            f"{name}_{col}" if name in monthly_returns and len(monthly_returns[name].columns) > 1 else col
            for name, df in monthly_returns.items()
            for col in df.columns
        ]
        combined_monthly.index.name = "date"

        # Fix column names
        all_cols = []
        col_idx = 0
        for name, df in monthly_returns.items():
            for col in df.columns:
                if len(df.columns) == 1:
                    all_cols.append(col)
                else:
                    all_cols.append(f"{name}_{col}")
        combined_monthly.columns = all_cols
        combined_monthly.index.name = "date"

        save_dataframe(combined_monthly, "indian_monthly_returns")
        print(f"\n  Saved: indian_monthly_returns ({len(combined_monthly)} months, {len(combined_monthly.columns)} columns)")

    if annual_returns:
        combined_annual = pd.concat(annual_returns.values(), axis=1)
        all_annual_cols = []
        for name, df in annual_returns.items():
            for col in df.columns:
                if len(df.columns) == 1:
                    all_annual_cols.append(col)
                else:
                    all_annual_cols.append(f"{name}_{col}")
        combined_annual.columns = all_annual_cols
        combined_annual.index.name = "date"

        save_dataframe(combined_annual, "indian_annual_returns")
        print(f"  Saved: indian_annual_returns ({len(combined_annual)} years)")

    # 5. Compute Statistics
    print("\n[5] Computing Statistics...")
    if monthly_returns:
        combined_monthly = load_data_file("indian_monthly_returns")
        if not combined_monthly.empty:
            stats = compute_asset_statistics(combined_monthly)
            save_dataframe(stats, "indian_asset_statistics")
            print(f"  Saved: indian_asset_statistics ({len(stats)} assets)")

            corr = compute_correlation_matrix(combined_monthly)
            if not corr.empty:
                save_dataframe(corr, "indian_correlation_matrix")
                print(f"  Saved: indian_correlation_matrix ({len(corr)}x{len(corr.columns)})")

            cov = compute_covariance_matrix(combined_monthly)
            if not cov.empty:
                save_dataframe(cov, "indian_covariance_matrix")
                print(f"  Saved: indian_covariance_matrix ({len(cov)}x{len(cov.columns)})")

    # 6. Save config
    print("\n[6] Saving Configuration...")
    save_config_summary()

    # 7. Generate report
    print("\n[7] Generating Report...")
    report = generate_summary_report()
    report_path = PROCESSED_DIR / "data_summary_report.txt"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"  Saved: data_summary_report.txt")

    print("\n" + "=" * 60)
    print("  PROCESSING COMPLETE")
    print(f"  Output: {PROCESSED_DIR}")
    print("=" * 60)

    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", action="store_true", help="Save config summary only")
    parser.add_argument("--report", action="store_true", help="Generate report only")
    parser.add_argument("--all", action="store_true", help="Run all processing")
    args = parser.parse_args()

    if args.all or args.config:
        save_config_summary()

    if args.all or args.report:
        report = generate_summary_report()
        print(report)

    if args.all or not (args.config or args.report):
        process_all_data()

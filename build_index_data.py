"""Rebuild the Monte Carlo engine's data pickles from:
- `data_index level/*_yfinance.csv`         (236 Indian indices)
- `data_stocks_nifty500/*_yfinance.csv`     (500 Nifty 500 constituent stocks)

Produces the same pickle-file schema the engine expects.

Bond/gilt exposure is intentionally dropped since the source CSVs contain
only equity/factor/sectoral indices and equity stocks.
"""
import re
import pandas as pd
import numpy as np
from pathlib import Path

INDEX_DIR = Path("data_index level")
STOCKS_DIR = Path("data_stocks_nifty500")
STOCKS_META = STOCKS_DIR / "metadata.csv"
OUT_DIR = Path("data/processed")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def alias_from_filename(name: str) -> str:
    """Convert 'nifty_50_yfinance.csv' -> 'NIFTY_50'."""
    stem = name.replace("_yfinance.csv", "")
    return stem.upper()


def category_from_alias(alias: str) -> str:
    """Rough categorization for UI grouping."""
    a = alias.lower()
    if any(k in a for k in ["bank", "psu_bank", "private_bank", "nbfc", "financial", "insurance",
                             "housing_finance", "capital_markets"]):
        return "financials"
    if any(k in a for k in ["it", "information_technology", "digital", "telecom"]):
        return "tech"
    if any(k in a for k in ["pharma", "healthcare", "hospital"]):
        return "healthcare"
    if any(k in a for k in ["auto", "mobility", "transportation"]):
        return "auto"
    if any(k in a for k in ["metal", "energy", "oil_and_gas", "power", "utilities",
                             "commodities", "commodity"]):
        return "energy_metals"
    if any(k in a for k in ["fmcg", "consumer_durables", "consumer_discretionary",
                             "non_cyclical_consumer", "retail"]):
        return "consumer"
    if any(k in a for k in ["realty", "reits", "infrastructure", "capital_goods",
                             "industrials", "manufacturing", "defence", "construction"]):
        return "industrials_realty"
    if any(k in a for k in ["media", "waves"]):
        return "media"
    if any(k in a for k in ["esg", "shariah", "dividend", "quality", "momentum", "value",
                             "growth", "low_volatility", "alpha", "beta", "enhanced",
                             "leaders", "size_weighted"]):
        return "factor_thematic"
    if any(k in a for k in ["midcap", "smallcap", "microcap"]):
        return "mid_small_cap"
    if any(k in a for k in ["largecap", "next_50", "top_10", "top_15", "top_20", "sensex",
                             "nifty_50", "nifty_100", "nifty_200", "nifty_500",
                             "bse_100", "bse_200", "bse_500", "bse_1000"]):
        return "large_cap"
    if a == "india_vix":
        return "volatility"
    return "broad_market"


def load_one_csv(path: Path) -> pd.DataFrame | None:
    """Load a single index CSV, return Series of daily returns indexed by Date, or None."""
    try:
        df = pd.read_csv(path, usecols=lambda c: c in ("Date", "Return"))
    except Exception as e:
        print(f"  skip {path.name}: read error {e}")
        return None
    if "Date" not in df.columns or "Return" not in df.columns:
        print(f"  skip {path.name}: missing Date/Return columns")
        return None
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True).dt.tz_convert(None)
    df = df.dropna(subset=["Date"])
    df = df.drop_duplicates(subset=["Date"])
    df["Return"] = pd.to_numeric(df["Return"], errors="coerce")
    df = df.dropna(subset=["Return"])
    if len(df) < 60:  # need at least a few months of data
        print(f"  skip {path.name}: only {len(df)} valid rows")
        return None
    df = df.set_index("Date").sort_index()
    return df["Return"].rename(alias_from_filename(path.name))


def daily_to_monthly(daily_returns: pd.Series) -> pd.Series:
    """Compound daily returns to month-end monthly returns."""
    monthly = (1 + daily_returns).resample("ME").prod() - 1
    return monthly


def main():
    # ── Load index CSVs ────────────────────────────────────────────────
    print(f"Reading CSVs from {INDEX_DIR}...")
    index_csvs = sorted(INDEX_DIR.glob("*_yfinance.csv"))
    print(f"  Found {len(index_csvs)} index CSV files")

    daily_series = []
    for csv in index_csvs:
        s = load_one_csv(csv)
        if s is not None:
            daily_series.append(s)
    print(f"  Loaded {len(daily_series)} indices with valid data")

    # ── Load stock CSVs ────────────────────────────────────────────────
    n_indices_loaded = len(daily_series)
    stock_aliases: set[str] = set()
    stock_industry_map: dict[str, str] = {}
    stock_display_map: dict[str, str] = {}

    if STOCKS_DIR.exists():
        print(f"\nReading stocks from {STOCKS_DIR}...")
        stock_csvs = sorted(STOCKS_DIR.glob("*_yfinance.csv"))
        print(f"  Found {len(stock_csvs)} stock CSV files")

        # Load metadata for per-stock industry + display name
        if STOCKS_META.exists():
            meta = pd.read_csv(STOCKS_META)
            for _, row in meta.iterrows():
                sym = str(row["symbol"]).strip()
                stock_industry_map[sym] = str(row.get("industry", "Unknown"))
                stock_display_map[sym] = str(row.get("name", sym))

        for csv in stock_csvs:
            s = load_one_csv(csv)
            if s is not None:
                daily_series.append(s)
                stock_aliases.add(alias_from_filename(csv.name))
        print(f"  Loaded {len(stock_aliases)} stocks with valid data")

    print(f"\nTotal series to merge: {len(daily_series)} "
          f"({n_indices_loaded} indices + {len(stock_aliases)} stocks)")

    # Merge all daily returns into a wide DataFrame (outer join on dates)
    print("Merging daily returns...")
    daily_wide = pd.concat(daily_series, axis=1)
    print(f"  Merged shape: {daily_wide.shape} (dates × indices)")

    # Compute month-end monthly returns per column
    print("Computing monthly returns...")
    monthly = pd.DataFrame(index=pd.date_range(daily_wide.index.min(),
                                                daily_wide.index.max(),
                                                freq="ME"))
    for col in daily_wide.columns:
        m = daily_to_monthly(daily_wide[col].dropna())
        monthly[col] = m
    monthly.index.name = None
    print(f"  Monthly returns shape: {monthly.shape}")

    # Filter out rows with no data at all
    monthly = monthly.dropna(how="all")

    # Compute annual returns per column (compound monthly returns per calendar year)
    print("Computing annual returns...")
    annual = pd.DataFrame(index=monthly.index.year.unique())
    for col in monthly.columns:
        s = monthly[col].dropna()
        yearly = (1 + s).groupby(s.index.year).prod() - 1
        annual[col] = yearly
    annual = annual.dropna(how="all")
    print(f"  Annual returns shape: {annual.shape}")

    # Compute per-asset statistics
    print("Computing asset statistics...")
    stats_rows = {}
    for col in monthly.columns:
        s = monthly[col].dropna()
        if len(s) < 12:
            continue
        mean_monthly = s.mean()
        std_monthly = s.std()
        # Annualize
        mean_ann = (1 + mean_monthly) ** 12 - 1
        std_ann = std_monthly * np.sqrt(12)
        # Geometric mean (CAGR)
        geo_ann = (np.prod(1 + s) ** (12 / len(s))) - 1 if (1 + s).prod() > 0 else 0.0
        # Max DD
        cum = (1 + s).cumprod()
        peak = cum.cummax()
        max_dd = ((cum - peak) / peak).min()
        # Skew, kurtosis
        skew = s.skew()
        kurt = s.kurtosis()
        n_months = len(s)
        n_years = n_months / 12
        stats_rows[col] = {
            "mean_annual": mean_ann,
            "std_annual": std_ann,
            "geo_mean_annual": geo_ann,
            "sharpe_ratio": (mean_ann - 0.0483) / std_ann if std_ann > 0 else 0.0,
            "max_drawdown": max_dd,
            "skewness": skew,
            "kurtosis": kurt,
            "best_month": s.max(),
            "worst_month": s.min(),
            "n_months": n_months,
            "n_years": n_years,
            "start_date": s.index.min(),
            "end_date": s.index.max(),
        }
    stats_df = pd.DataFrame(stats_rows).T
    print(f"  Stats shape: {stats_df.shape}")

    # Filter monthly returns to only include indices that made it into stats
    monthly = monthly[stats_df.index]
    annual = annual[[c for c in stats_df.index if c in annual.columns]]

    # Correlation matrix
    print("Computing correlation matrix...")
    corr = monthly.corr()
    print(f"  Correlation shape: {corr.shape}")

    # Covariance matrix (annualized)
    print("Computing covariance matrix...")
    cov = monthly.cov() * 12
    print(f"  Covariance shape: {cov.shape}")

    # Save pickles with the same names the engine expects
    print(f"\nSaving to {OUT_DIR}/...")
    monthly.to_pickle(OUT_DIR / "all_monthly_returns_final.pkl")
    annual.to_pickle(OUT_DIR / "all_annual_returns_final.pkl")
    stats_df.to_pickle(OUT_DIR / "all_asset_statistics_final.pkl")
    corr.to_pickle(OUT_DIR / "all_correlation_matrix_final.pkl")
    cov.to_pickle(OUT_DIR / "all_covariance_matrix_final.pkl")
    print("  Saved 5 pickles")

    # Also save an "all_prices_final" placeholder — the engine's __init__ imports it
    # from loader but only some paths use it (currently not used in the sim run path).
    # Save an empty stub to prevent import errors.
    prices = pd.DataFrame(index=monthly.index)
    prices.to_pickle(OUT_DIR / "all_prices_final.pkl")

    # ── Build alias mapping ──────────────────────────────────────────
    def category_for(alias: str) -> str:
        # Stocks: use Industry from metadata; prefix "stock:" so UI can group
        if alias in stock_aliases:
            ind = stock_industry_map.get(alias, "Unknown")
            slug = re.sub(r"[^a-z0-9]+", "_", ind.lower()).strip("_") or "unknown"
            return f"stock_{slug}"
        # Indices: rule-based category
        return category_from_alias(alias)

    def display_for(alias: str) -> str:
        if alias in stock_aliases and alias in stock_display_map:
            # Strip "Ltd."/"Limited" suffix, escape quotes
            name = stock_display_map[alias]
            name = re.sub(r"\s+(Ltd\.?|Limited)$", "", name, flags=re.IGNORECASE)
            return name.replace('"', "'").strip()
        return alias.replace("_", " ").title()

    print("\n=== Alias summary ===")
    cats = {}
    for alias in stats_df.index:
        c = category_for(alias)
        cats.setdefault(c, []).append(alias)
    for c in sorted(cats.keys()):
        kind = "stocks" if c.startswith("stock_") else "indices"
        print(f"  [{c}] {len(cats[c])} {kind}")

    mapping_lines = ["# Auto-generated by build_index_data.py",
                     "# alias -> (data_code, category, display_name)",
                     "INDEX_MAPPING = {"]
    for alias in sorted(stats_df.index):
        cat = category_for(alias)
        display = display_for(alias)
        mapping_lines.append(
            f'    "{alias}": ("{alias}", "{cat}", "{display}"),'
        )
    mapping_lines.append("}")
    mapping_file = Path("macrowise/data/_generated_index_mapping.py")
    mapping_file.write_text("\n".join(mapping_lines))
    print(f"\n  Wrote {mapping_file}")


if __name__ == "__main__":
    main()

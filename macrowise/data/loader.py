"""
Data loader module - loads cleaned Indian market data from pickle files.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import os

# Default data directory (relative to repo root)
from pathlib import Path
import os

_DEFAULT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_DATA_DIR = _DEFAULT_ROOT / "data" / "processed"


def set_data_directory(path: str | Path) -> None:
    """Override the default data directory and clear caches."""
    global _DATA_DIR
    _DATA_DIR = Path(path)
    clear_cache()


def get_data_directory() -> Path:
    """Get the current data directory."""
    return _DATA_DIR


def load_prices() -> pd.DataFrame:
    """Load all price series (daily, 2000-2026)."""
    return pd.read_pickle(_DATA_DIR / "all_prices_final.pkl")


def load_monthly_returns() -> pd.DataFrame:
    """Load monthly percentage returns (317 months, 134 assets)."""
    return pd.read_pickle(_DATA_DIR / "all_monthly_returns_final.pkl")


def load_annual_returns() -> pd.DataFrame:
    """Load annual returns (27 years, 134 assets)."""
    return pd.read_pickle(_DATA_DIR / "all_annual_returns_final.pkl")


def load_asset_statistics() -> pd.DataFrame:
    """Load per-asset statistics (13 metrics per asset)."""
    return pd.read_pickle(_DATA_DIR / "all_asset_statistics_final.pkl")


def load_correlation_matrix() -> pd.DataFrame:
    """Load 134x134 Pearson correlation matrix (monthly returns)."""
    return pd.read_pickle(_DATA_DIR / "all_correlation_matrix_final.pkl")


def load_covariance_matrix() -> pd.DataFrame:
    """Load 134x134 annualized covariance matrix."""
    return pd.read_pickle(_DATA_DIR / "all_covariance_matrix_final.pkl")


def load_inflation_data() -> pd.Series:
    """Load Indian CPI monthly data as a Series (converts from DataFrame if needed)."""
    obj = pd.read_pickle(_DATA_DIR / "inflation_data.pkl")
    if isinstance(obj, pd.DataFrame):
        # Take first column, assuming inflation rate
        obj = obj.iloc[:, 0].copy()
    elif not isinstance(obj, pd.Series):
        obj = pd.Series(obj)
    if getattr(obj, "name", None) is None:
        obj.name = "CPI"
    return obj


def load_dynamic_rf() -> pd.DataFrame:
    """Load dynamic risk-free rate series (RBI repo-based)."""
    return pd.read_pickle(_DATA_DIR / "dynamic_risk_free_rate.pkl")


def load_life_expectancy() -> pd.DataFrame:
    """Load Indian life expectancy data."""
    return pd.read_pickle(_DATA_DIR / "life_expectancy_india.pkl")


# Lazy load cache
_prices_cache = None
_monthly_returns_cache = None
_annual_returns_cache = None
_asset_statistics_cache = None
_correlation_matrix_cache = None
_covariance_matrix_cache = None


def get_prices() -> pd.DataFrame:
    """Cached version of load_prices()."""
    global _prices_cache
    if _prices_cache is None:
        _prices_cache = load_prices()
    return _prices_cache


def get_monthly_returns() -> pd.DataFrame:
    """Cached version of load_monthly_returns()."""
    global _monthly_returns_cache
    if _monthly_returns_cache is None:
        _monthly_returns_cache = load_monthly_returns()
    return _monthly_returns_cache


def get_annual_returns() -> pd.DataFrame:
    """Cached version of load_annual_returns()."""
    global _annual_returns_cache
    if _annual_returns_cache is None:
        _annual_returns_cache = load_annual_returns()
    return _annual_returns_cache


def get_asset_statistics() -> pd.DataFrame:
    """Cached version of load_asset_statistics()."""
    global _asset_statistics_cache
    if _asset_statistics_cache is None:
        _asset_statistics_cache = load_asset_statistics()
    return _asset_statistics_cache


def get_correlation_matrix() -> pd.DataFrame:
    """Cached version of load_correlation_matrix()."""
    global _correlation_matrix_cache
    if _correlation_matrix_cache is None:
        _correlation_matrix_cache = load_correlation_matrix()
    return _correlation_matrix_cache


def get_covariance_matrix() -> pd.DataFrame:
    """Cached version of load_covariance_matrix()."""
    global _covariance_matrix_cache
    if _covariance_matrix_cache is None:
        _covariance_matrix_cache = load_covariance_matrix()
    return _covariance_matrix_cache


def clear_cache() -> None:
    """Clear all cached data."""
    global _prices_cache, _monthly_returns_cache, _annual_returns_cache
    global _asset_statistics_cache, _correlation_matrix_cache, _covariance_matrix_cache
    _prices_cache = None
    _monthly_returns_cache = None
    _annual_returns_cache = None
    _asset_statistics_cache = None
    _correlation_matrix_cache = None
    _covariance_matrix_cache = None

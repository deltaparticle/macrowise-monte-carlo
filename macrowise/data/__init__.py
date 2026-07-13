from macrowise.data.loader import (
    get_prices,
    get_monthly_returns,
    get_annual_returns,
    get_asset_statistics,
    get_correlation_matrix,
    get_covariance_matrix,
    load_inflation_data,
    load_dynamic_rf,
    load_life_expectancy,
    set_data_directory,
    get_data_directory,
    clear_cache,
)
from macrowise.data.asset_registry import (
    get_asset,
    get_asset_name,
    assets_in_category,
    list_categories,
    list_asset_aliases,
    get_asset_data_code,
    resolve_assets,
    AssetInfo,
)


def register_asset(code, info):
    pass


__all__ = [
    "get_prices", "get_monthly_returns", "get_annual_returns",
    "get_asset_statistics", "get_correlation_matrix", "get_covariance_matrix",
    "load_inflation_data", "load_dynamic_rf", "load_life_expectancy",
    "set_data_directory", "get_data_directory", "clear_cache",
    "get_asset", "get_asset_name", "assets_in_category", "list_categories",
    "list_asset_aliases", "get_asset_data_code", "register_asset",
    "resolve_assets", "AssetInfo",
]

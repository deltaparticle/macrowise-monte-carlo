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
    get_assets_by_category,
    list_categories,
    list_asset_aliases,
    list_data_codes,
    get_asset_data_code,
    get_default_portfolio_60_40,
    get_all_codes,
    resolve_assets,
    PV_TO_INDIAN_ALIAS,
    AssetInfo,
)


def register_asset(code: str, info: AssetInfo) -> None:
    """Stub — custom assets can be added via direct data loading."""
    pass

__all__ = [
    "get_prices",
    "get_monthly_returns",
    "get_annual_returns",
    "get_asset_statistics",
    "get_correlation_matrix",
    "get_covariance_matrix",
    "load_inflation_data",
    "load_dynamic_rf",
    "load_life_expectancy",
    "set_data_directory",
    "get_data_directory",
    "clear_cache",
    "get_asset",
    "get_asset_name",
    "get_assets_by_category",
    "list_categories",
    "list_asset_aliases",
    "list_data_codes",
    "get_asset_data_code",
    "register_asset",
    "get_default_portfolio_60_40",
    "get_all_codes",
    "resolve_assets",
    "PV_TO_INDIAN_ALIAS",
    "AssetInfo",
]

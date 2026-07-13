"""Asset Registry — maps display aliases to actual data column names.

Data source: 262 Indian equity/factor/sectoral indices from `data_index level/`
(NSE + BSE). No mutual funds, no individual stocks, no ETFs, no bond data.

Aliases are UPPER_SNAKE_CASE index names (e.g. NIFTY_50, BSE_500,
NIFTY_MIDCAP_150, NIFTY_MOMENTUM_50).
"""

from dataclasses import dataclass
from typing import Optional

from macrowise.data._generated_index_mapping import INDEX_MAPPING


@dataclass
class AssetInfo:
    """Metadata about a single asset (index)."""
    alias: str
    name: str
    category: str
    data_code: str
    default_mean: Optional[float] = None
    default_std: Optional[float] = None


# Build the alias -> data_code map
_ALIAS_TO_DATA_CODE: dict[str, str] = {
    alias: data_code for alias, (data_code, _cat, _name) in INDEX_MAPPING.items()
}

# Build the full asset info map
_ASSETS: dict[str, AssetInfo] = {
    alias: AssetInfo(
        alias=alias,
        name=display_name,
        category=category,
        data_code=data_code,
    )
    for alias, (data_code, category, display_name) in INDEX_MAPPING.items()
}


# ── Public API ───────────────────────────────────────────────────────────

def get_asset(alias: str) -> Optional[AssetInfo]:
    """Get full metadata for an asset by alias or data code."""
    if alias in _ASSETS:
        return _ASSETS[alias]
    for info in _ASSETS.values():
        if info.data_code == alias:
            return info
    return None


def get_asset_name(alias: str) -> str:
    info = get_asset(alias)
    return info.name if info else alias


def get_asset_data_code(alias: str) -> Optional[str]:
    """Resolve an alias to the actual pickle-column name."""
    if alias in _ALIAS_TO_DATA_CODE:
        return _ALIAS_TO_DATA_CODE[alias]
    if alias in {info.data_code for info in _ASSETS.values()}:
        return alias
    return None


def list_asset_aliases() -> list[str]:
    return sorted(_ALIAS_TO_DATA_CODE.keys())


def resolve_assets(aliases_and_weights: list[tuple[str, float]]) -> list[tuple[str, float]]:
    resolved = []
    for alias, weight in aliases_and_weights:
        code = get_asset_data_code(alias)
        if code is None:
            raise ValueError(f"Unknown asset alias: '{alias}'")
        resolved.append((code, weight))
    return resolved


def list_categories() -> list[str]:
    return sorted({info.category for info in _ASSETS.values()})


def assets_in_category(category: str) -> list[str]:
    return sorted([a for a, info in _ASSETS.items() if info.category == category])

"""
Asset Registry — maps display names / aliases to actual data column names.

All codes in this registry MUST match the actual column names in the pickle files.
The registry provides:
  1. User-friendly ALIASES (short codes) that map to actual data column names
  2. Full metadata (name, category, default mean/std) per asset
  3. PV → Indian asset mapping

Data source files (in data/processed/):
  - all_monthly_returns_final.pkl     (134 columns)
  - all_annual_returns_final.pkl
  - all_asset_statistics_final.pkl
  - all_correlation_matrix_final.pkl
  - all_covariance_matrix_final.pkl
"""

from dataclasses import dataclass
from typing import Optional


# ── Alias → Actual Data Column Mapping ─────────────────────────────────────
# These are the SHORT codes that users pass to MonteCarloConfig.assets
_ALIAS_TO_DATA_CODE: dict[str, str] = {}

# ── Common User Aliases (short, memorable) ───────────────────────────────────
# Equity
_ALIAS_TO_DATA_CODE["NIFTY_50"] = "TRI_NIFTY_50_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_BANK"] = "TRI_NIFTY_BANK_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_IT"] = "TRI_NIFTY_IT_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_PHARMA"] = "TRI_NIFTY_PHARMA_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_FMCG"] = "TRI_NIFTY_FMCG_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_AUTO"] = "TRI_NIFTY_AUTO_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_MIDCAP"] = "TRI_NIFTY_MIDCAP_100_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_SMALLCAP"] = "TRI_NIFTY_SMALLCAP_100_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_REALTY"] = "TRI_NIFTY_REALTY_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_METAL"] = "TRI_NIFTY_METAL_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_ENERGY"] = "TRI_NIFTY_ENERGY_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_FINSERV"] = "TRI_NIFTY_FIN_SERVICE_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["NIFTY_INFRA"] = "TRI_NIFTY_INFRA_TotalReturnsIndex"
_ALIAS_TO_DATA_CODE["SENSEX"] = "BSE_SENSEX"

# Bonds / Gilt
_ALIAS_TO_DATA_CODE["SBI_GILT"] = "mf_nav_MF_Gilt_SBI_GILT_FUND___DIRECT_PLAN___"
_ALIAS_TO_DATA_CODE["ICICI_GILT"] = "mf_nav_MF_Gilt_ICICI_Prudential_Gilt_Fund___D"
_ALIAS_TO_DATA_CODE["HDFC_GILT"] = "mf_nav_MF_Gilt_HDFC_Gilt_Fund___Growth_Option"
_ALIAS_TO_DATA_CODE["UTI_GILT"] = "mf_nav_MF_Gilt_UTI_Gilt_Fund___Direct_Plan___"
_ALIAS_TO_DATA_CODE["SBI_CORP"] = "mf_nav_MF_CorpBond_SBI_Corporate_Bond_Fund___Dire"
_ALIAS_TO_DATA_CODE["HDFC_CORP"] = "mf_nav_MF_CorpBond_HDFC_Corporate_Bond_Fund___Gro"
_ALIAS_TO_DATA_CODE["NIPPON_CORP"] = "mf_nav_MF_CorpBond_NIPPON_INDIA_CORPORATE_BOND_FU"
_ALIAS_TO_DATA_CODE["UTI_CORP"] = "mf_nav_MF_CorpBond_UTI_Corporate_Bond_Fund___Dire"
_ALIAS_TO_DATA_CODE["ADITYA_DYNAMIC"] = "mf_nav_MF_DynamicBond_Aditya_Birla_Sun_Life_Dynamic_"
_ALIAS_TO_DATA_CODE["KOTAK_DYNAMIC"] = "mf_nav_MF_DynamicBond_Kotak_Dynamic_Bond_Fund___Dire"
_ALIAS_TO_DATA_CODE["NIPPON_DYNAMIC"] = "mf_nav_MF_DynamicBond_NIPPON_INDIA_DYNAMIC_BOND_FUND"
_ALIAS_TO_DATA_CODE["SBI_BALANCED"] = "mf_nav_MF_Balanced_SBI_Balanced_Advantage_Fund___"
_ALIAS_TO_DATA_CODE["HDFC_BALANCED"] = "mf_nav_MF_Balanced_HDFC_Balanced_Advantage_Fund__"
_ALIAS_TO_DATA_CODE["PPFAS_FLEXI"] = "mf_nav_MF_FlexiCap_Parag_Parikh_Flexi_Cap_Fund___"

# Gold / Commodities
_ALIAS_TO_DATA_CODE["GOLD"] = "GOLD_INR_ETF"
_ALIAS_TO_DATA_CODE["GOLD_USD"] = "GOLD_USD"
_ALIAS_TO_DATA_CODE["SILVER"] = "SILVER_INR_ETF"
_ALIAS_TO_DATA_CODE["CRUDE"] = "CRUDE_WTI"

# Liquid
_ALIAS_TO_DATA_CODE["SBI_LIQUID"] = "mf_nav_MF_Liquid_SBI_Liquid_Fund___Direct_Paln_"
_ALIAS_TO_DATA_CODE["UTI_LIQUID"] = "mf_nav_MF_Liquid_UTI_Liquid_Fund___Direct_Plan_"

# Stocks
_ALIAS_TO_DATA_CODE["RELIANCE"] = "STOCK_RELIANCE"
_ALIAS_TO_DATA_CODE["TCS"] = "STOCK_TCS"
_ALIAS_TO_DATA_CODE["HDFCBANK"] = "STOCK_HDFCBANK"
_ALIAS_TO_DATA_CODE["INFY"] = "STOCK_INFY"
_ALIAS_TO_DATA_CODE["ICICIBANK"] = "STOCK_ICICIBANK"
_ALIAS_TO_DATA_CODE["HUL"] = "STOCK_HUL"
_ALIAS_TO_DATA_CODE["SBIN"] = "STOCK_SBIN"
_ALIAS_TO_DATA_CODE["BHARTIARTL"] = "STOCK_BHARTIARTL"
_ALIAS_TO_DATA_CODE["LT"] = "STOCK_LT"
_ALIAS_TO_DATA_CODE["ITC"] = "STOCK_ITC"
_ALIAS_TO_DATA_CODE["BAJFINANCE"] = "STOCK_BAJFINANCE"
_ALIAS_TO_DATA_CODE["KOTAKBANK"] = "STOCK_KOTAKBANK"
_ALIAS_TO_DATA_CODE["TATAMOTORS"] = "STOCK_TATAMOTORS"
_ALIAS_TO_DATA_CODE["TITAN"] = "STOCK_TITAN"
_ALIAS_TO_DATA_CODE["SUNPHARMA"] = "STOCK_SUNPHARMA"
_ALIAS_TO_DATA_CODE["NESTLEIND"] = "STOCK_NESTLEIND"
_ALIAS_TO_DATA_CODE["PERSISTENT"] = "STOCK_PERSISTENT"
_ALIAS_TO_DATA_CODE["INDUSINDBK"] = "STOCK_INDUSINDBK"

# ETFs
_ALIAS_TO_DATA_CODE["NIFTYBEES"] = "ETF_NIFTY50"
_ALIAS_TO_DATA_CODE["GOLDBEES"] = "ETF_GOLD"
_ALIAS_TO_DATA_CODE["LIQUIDBEES"] = "ETF_LIQUID"
_ALIAS_TO_DATA_CODE["NIPPON_IT"] = "ETF_NIFTYIT"
_ALIAS_TO_DATA_CODE["NIPPON_BANK"] = "ETF_NIFTYBANK"

# Index funds
_ALIAS_TO_DATA_CODE["HDFC_NIFTY50"] = "mf_nav_MF_IndexFunds_HDFC_Nifty_50_Index_Fund___Dir"
_ALIAS_TO_DATA_CODE["ICICI_NIFTY50"] = "mf_nav_MF_IndexFunds_ICICI_Prudential_Nifty_50_Inde"

# Large/Mid/Small Cap MFs
_ALIAS_TO_DATA_CODE["MIRAE_LARGECAP"] = "mf_nav_MF_LargeCap_Mirae_Asset_Large_Cap_Fund___D"
_ALIAS_TO_DATA_CODE["NIPPON_MIDCAP"] = "mf_nav_MF_MidCap_NIPPON_INDIA_BANKING_and_PSU__"
_ALIAS_TO_DATA_CODE["NIPPON_SMALLCAP"] = "mf_nav_MF_SmallCap_NIPPON_INDIA_SMALL_CAP_FUND___"
_ALIAS_TO_DATA_CODE["SBI_SMALLCAP"] = "mf_nav_MF_MidCap_SBI_Small_Cap_Fund___Direct_Pl"
_ALIAS_TO_DATA_CODE["AXIS_SMALLCAP"] = "mf_nav_MF_SmallCap_Axis_Small_Cap_Fund___Direct_P"
_ALIAS_TO_DATA_CODE["DSP_SMALLCAP"] = "mf_nav_MF_SmallCap_DSP_Small_Cap_Fund___Direct_Pl"
_ALIAS_TO_DATA_CODE["HDFC_SMALLCAP"] = "mf_nav_MF_SmallCap_HDFC_Small_Cap_Fund___Growth_O"
_ALIAS_TO_DATA_CODE["ICICI_SMALLCAP"] = "mf_nav_MF_SmallCap_ICICI_Prudential_Smallcap_Fund"
_ALIAS_TO_DATA_CODE["NIPPON_PHARMA"] = "mf_nav_MF_Sectoral_NIPPON_INDIA_PHARMA_FUND___DIR"
_ALIAS_TO_DATA_CODE["TATA_DIGITAL"] = "mf_nav_MF_Sectoral_TATA_Digital_India_Fund_Direct"


# ── PV → Indian Alias Mapping ───────────────────────────────────────────────
# Maps PortfolioVisualizer asset IDs to our aliases
PV_TO_INDIAN_ALIAS = {
    "TotalStockMarket": "NIFTY_50",
    "LargeCapBlend": "NIFTY_50",
    "LargeCapValue": "HDFCBANK",
    "LargeCapGrowth": "TCS",
    "MidCapBlend": "NIFTY_MIDCAP",
    "SmallCapBlend": "NIFTY_SMALLCAP",
    "MicroCap": None,
    "IntlStockMarket": None,
    "IntlDeveloped": None,
    "IntlSmall": None,
    "IntlValue": None,
    "Europe": None,
    "Pacific": None,
    "EmergingMarket": "NIFTY_MIDCAP",
    "TreasuryBills": "SBI_LIQUID",
    "ShortTreasury": "SBI_LIQUID",
    "IntermediateTreasury": "SBI_CORP",
    "TreasuryNotes": "SBI_GILT",
    "LongTreasury": "ICICI_GILT",
    "TotalBond": "SBI_CORP",
    "TIPS": None,
    "GlobalBond": None,
    "GlobalBondHedged": None,
    "ShortInvBond": "HDFC_CORP",
    "CorpBond": "SBI_CORP",
    "LongCorpBond": "HDFC_CORP",
    "HighYield": None,
    "ShortTaxExempt": None,
    "InterTaxExempt": None,
    "LongTaxExempt": None,
    "REIT": "NIFTY_REALTY",
    "Gold": "GOLD",
    "PreciousMetals": "SILVER",
    "Commodities": "CRUDE",
}


@dataclass
class AssetInfo:
    """Metadata for a single asset."""
    code: str          # Actual data column name
    alias: str         # Short user-friendly alias
    name: str          # Clean display name
    category: str      # Asset category
    default_mean: float
    default_std: float


# ── Asset Metadata (values from all_asset_statistics_final.pkl) ─────────────
# mean and std are from actual historical data
_ALL_ASSETS: dict[str, AssetInfo] = {}

# NSE TRI Indices
_ALL_ASSETS["TRI_NIFTY_50_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_50_TotalReturnsIndex", alias="NIFTY_50",
    name="Nifty 50 TRI", category="indian_equity", default_mean=15.06, default_std=21.56)
_ALL_ASSETS["TRI_NIFTY_BANK_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_BANK_TotalReturnsIndex", alias="NIFTY_BANK",
    name="Nifty Bank TRI", category="indian_equity", default_mean=22.59, default_std=29.59)
_ALL_ASSETS["TRI_NIFTY_IT_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_IT_TotalReturnsIndex", alias="NIFTY_IT",
    name="Nifty IT TRI", category="indian_equity", default_mean=13.77, default_std=32.38)
_ALL_ASSETS["TRI_NIFTY_PHARMA_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_PHARMA_TotalReturnsIndex", alias="NIFTY_PHARMA",
    name="Nifty Pharma TRI", category="indian_equity", default_mean=17.12, default_std=21.00)
_ALL_ASSETS["TRI_NIFTY_FMCG_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_FMCG_TotalReturnsIndex", alias="NIFTY_FMCG",
    name="Nifty FMCG TRI", category="indian_equity", default_mean=14.98, default_std=18.96)
_ALL_ASSETS["TRI_NIFTY_AUTO_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_AUTO_TotalReturnsIndex", alias="NIFTY_AUTO",
    name="Nifty Auto TRI", category="indian_equity", default_mean=21.06, default_std=25.40)
_ALL_ASSETS["TRI_NIFTY_MIDCAP_100_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_MIDCAP_100_TotalReturnsIndex", alias="NIFTY_MIDCAP",
    name="Nifty Midcap 100 TRI", category="indian_equity", default_mean=24.99, default_std=25.85)
_ALL_ASSETS["TRI_NIFTY_SMALLCAP_100_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_SMALLCAP_100_TotalReturnsIndex", alias="NIFTY_SMALLCAP",
    name="Nifty Smallcap 100 TRI", category="indian_equity", default_mean=21.23, default_std=29.49)
_ALL_ASSETS["TRI_NIFTY_REALTY_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_REALTY_TotalReturnsIndex", alias="NIFTY_REALTY",
    name="Nifty Realty TRI", category="indian_equity", default_mean=10.71, default_std=46.92)
_ALL_ASSETS["TRI_NIFTY_METAL_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_METAL_TotalReturnsIndex", alias="NIFTY_METAL",
    name="Nifty Metal TRI", category="indian_equity", default_mean=22.53, default_std=36.28)
_ALL_ASSETS["TRI_NIFTY_ENERGY_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_ENERGY_TotalReturnsIndex", alias="NIFTY_ENERGY",
    name="Nifty Energy TRI", category="indian_equity", default_mean=21.43, default_std=25.83)
_ALL_ASSETS["TRI_NIFTY_FIN_SERVICE_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_FIN_SERVICE_TotalReturnsIndex", alias="NIFTY_FINSERV",
    name="Nifty Financial Services TRI", category="indian_equity", default_mean=21.65, default_std=28.18)
_ALL_ASSETS["TRI_NIFTY_INFRA_TotalReturnsIndex"] = AssetInfo(
    code="TRI_NIFTY_INFRA_TotalReturnsIndex", alias="NIFTY_INFRA",
    name="Nifty Infrastructure TRI", category="indian_equity", default_mean=15.49, default_std=25.82)
_ALL_ASSETS["BSE_SENSEX"] = AssetInfo(
    code="BSE_SENSEX", alias="SENSEX",
    name="BSE Sensex", category="indian_equity", default_mean=13.23, default_std=21.22)
_ALL_ASSETS["INDIA_VIX"] = AssetInfo(
    code="INDIA_VIX", alias="INDIA_VIX",
    name="India VIX", category="indian_equity", default_mean=26.60, default_std=85.18)

# Stocks
_ALL_ASSETS["STOCK_RELIANCE"] = AssetInfo(
    code="STOCK_RELIANCE", alias="RELIANCE",
    name="Reliance Industries", category="indian_equity", default_mean=22.78, default_std=29.41)
_ALL_ASSETS["STOCK_TCS"] = AssetInfo(
    code="STOCK_TCS", alias="TCS",
    name="Tata Consultancy Services", category="indian_equity", default_mean=26.07, default_std=35.28)
_ALL_ASSETS["STOCK_HDFCBANK"] = AssetInfo(
    code="STOCK_HDFCBANK", alias="HDFCBANK",
    name="HDFC Bank", category="indian_equity", default_mean=22.15, default_std=25.71)
_ALL_ASSETS["STOCK_INFY"] = AssetInfo(
    code="STOCK_INFY", alias="INFY",
    name="Infosys", category="indian_equity", default_mean=16.79, default_std=32.10)
_ALL_ASSETS["STOCK_ICICIBANK"] = AssetInfo(
    code="STOCK_ICICIBANK", alias="ICICIBANK",
    name="ICICI Bank", category="indian_equity", default_mean=27.46, default_std=35.89)
_ALL_ASSETS["STOCK_HUL"] = AssetInfo(
    code="STOCK_HUL", alias="HUL",
    name="Hindustan Unilever", category="indian_equity", default_mean=14.63, default_std=25.36)
_ALL_ASSETS["STOCK_SBIN"] = AssetInfo(
    code="STOCK_SBIN", alias="SBIN",
    name="State Bank of India", category="indian_equity", default_mean=25.12, default_std=36.66)
_ALL_ASSETS["STOCK_BHARTIARTL"] = AssetInfo(
    code="STOCK_BHARTIARTL", alias="BHARTIARTL",
    name="Bharti Airtel", category="indian_equity", default_mean=28.87, default_std=31.18)
_ALL_ASSETS["STOCK_LT"] = AssetInfo(
    code="STOCK_LT", alias="LT",
    name="Larsen & Toubro", category="indian_equity", default_mean=18.50, default_std=30.00)
_ALL_ASSETS["STOCK_ITC"] = AssetInfo(
    code="STOCK_ITC", alias="ITC",
    name="ITC Limited", category="indian_equity", default_mean=15.00, default_std=28.00)
_ALL_ASSETS["STOCK_INDUSINDBK"] = AssetInfo(
    code="STOCK_INDUSINDBK", alias="INDUSINDBK",
    name="IndusInd Bank", category="indian_equity", default_mean=34.71, default_std=47.67)
_ALL_ASSETS["STOCK_KOTAKBANK"] = AssetInfo(
    code="STOCK_KOTAKBANK", alias="KOTAKBANK",
    name="Kotak Mahindra Bank", category="indian_equity", default_mean=20.00, default_std=28.00)
_ALL_ASSETS["STOCK_TATAMOTORS"] = AssetInfo(
    code="STOCK_TATAMOTORS", alias="TATAMOTORS",
    name="Tata Motors", category="indian_equity", default_mean=25.00, default_std=40.00)
_ALL_ASSETS["STOCK_TITAN"] = AssetInfo(
    code="STOCK_TITAN", alias="TITAN",
    name="Titan Company", category="indian_equity", default_mean=22.00, default_std=32.00)
_ALL_ASSETS["STOCK_SUNPHARMA"] = AssetInfo(
    code="STOCK_SUNPHARMA", alias="SUNPHARMA",
    name="Sun Pharma", category="indian_equity", default_mean=16.00, default_std=28.00)
_ALL_ASSETS["STOCK_NESTLEIND"] = AssetInfo(
    code="STOCK_NESTLEIND", alias="NESTLEIND",
    name="Nestle India", category="indian_equity", default_mean=17.00, default_std=24.00)
_ALL_ASSETS["STOCK_PERSISTENT"] = AssetInfo(
    code="STOCK_PERSISTENT", alias="PERSISTENT",
    name="Persistent Systems", category="indian_equity", default_mean=36.20, default_std=36.88)

# Gilt / Bonds
_ALL_ASSETS["mf_nav_MF_Gilt_SBI_GILT_FUND___DIRECT_PLAN___"] = AssetInfo(
    code="mf_nav_MF_Gilt_SBI_GILT_FUND___DIRECT_PLAN___", alias="SBI_GILT",
    name="SBI Gilt Fund (Direct)", category="indian_bond", default_mean=8.90, default_std=4.07)
_ALL_ASSETS["mf_nav_MF_Gilt_ICICI_Prudential_Gilt_Fund___D"] = AssetInfo(
    code="mf_nav_MF_Gilt_ICICI_Prudential_Gilt_Fund___D", alias="ICICI_GILT",
    name="ICICI Prudential Gilt Fund", category="indian_bond", default_mean=8.57, default_std=4.76)
_ALL_ASSETS["mf_nav_MF_Gilt_HDFC_Gilt_Fund___Growth_Option"] = AssetInfo(
    code="mf_nav_MF_Gilt_HDFC_Gilt_Fund___Growth_Option", alias="HDFC_GILT",
    name="HDFC Gilt Fund (Growth)", category="indian_bond", default_mean=7.52, default_std=4.41)
_ALL_ASSETS["mf_nav_MF_Gilt_UTI_Gilt_Fund___Direct_Plan___"] = AssetInfo(
    code="mf_nav_MF_Gilt_UTI_Gilt_Fund___Direct_Plan___", alias="UTI_GILT",
    name="UTI Gilt Fund (Direct)", category="indian_bond", default_mean=5.81, default_std=4.45)
_ALL_ASSETS["mf_nav_MF_CorpBond_SBI_Corporate_Bond_Fund___Dire"] = AssetInfo(
    code="mf_nav_MF_CorpBond_SBI_Corporate_Bond_Fund___Dire", alias="SBI_CORP",
    name="SBI Corporate Bond Fund", category="indian_bond", default_mean=7.32, default_std=1.82)
_ALL_ASSETS["mf_nav_MF_CorpBond_HDFC_Corporate_Bond_Fund___Gro"] = AssetInfo(
    code="mf_nav_MF_CorpBond_HDFC_Corporate_Bond_Fund___Gro", alias="HDFC_CORP",
    name="HDFC Corporate Bond Fund", category="indian_bond", default_mean=7.99, default_std=2.07)
_ALL_ASSETS["mf_nav_MF_CorpBond_UTI_Corporate_Bond_Fund___Dire"] = AssetInfo(
    code="mf_nav_MF_CorpBond_UTI_Corporate_Bond_Fund___Dire", alias="UTI_CORP",
    name="UTI Corporate Bond Fund", category="indian_bond", default_mean=4.26, default_std=3.65)
_ALL_ASSETS["mf_nav_MF_DynamicBond_Aditya_Birla_Sun_Life_Dynamic_"] = AssetInfo(
    code="mf_nav_MF_DynamicBond_Aditya_Birla_Sun_Life_Dynamic_", alias="ADITYA_DYNAMIC",
    name="Aditya Birla Dynamic Bond Fund", category="indian_bond", default_mean=7.75, default_std=3.88)
_ALL_ASSETS["mf_nav_MF_DynamicBond_Kotak_Dynamic_Bond_Fund___Dire"] = AssetInfo(
    code="mf_nav_MF_DynamicBond_Kotak_Dynamic_Bond_Fund___Dire", alias="KOTAK_DYNAMIC",
    name="Kotak Dynamic Bond Fund", category="indian_bond", default_mean=3.10, default_std=4.65)
_ALL_ASSETS["mf_nav_MF_DynamicBond_NIPPON_INDIA_DYNAMIC_BOND_FUND"] = AssetInfo(
    code="mf_nav_MF_DynamicBond_NIPPON_INDIA_DYNAMIC_BOND_FUND", alias="NIPPON_DYNAMIC",
    name="Nippon India Dynamic Bond Fund", category="indian_bond", default_mean=5.68, default_std=5.11)

# Liquid
_ALL_ASSETS["mf_nav_MF_Liquid_SBI_Liquid_Fund___Direct_Paln_"] = AssetInfo(
    code="mf_nav_MF_Liquid_SBI_Liquid_Fund___Direct_Paln_", alias="SBI_LIQUID",
    name="SBI Liquid Fund (Direct)", category="indian_liquid", default_mean=2.75, default_std=0.90)
_ALL_ASSETS["mf_nav_MF_Liquid_UTI_Liquid_Fund___Direct_Plan_"] = AssetInfo(
    code="mf_nav_MF_Liquid_UTI_Liquid_Fund___Direct_Plan_", alias="UTI_LIQUID",
    name="UTI Liquid Fund (Direct)", category="indian_liquid", default_mean=-1.84, default_std=26.99)

# Gold / Commodities
_ALL_ASSETS["GOLD_INR_ETF"] = AssetInfo(
    code="GOLD_INR_ETF", alias="GOLD",
    name="Gold INR ETF (GOLDBEES)", category="commodities", default_mean=14.18, default_std=15.10)
_ALL_ASSETS["GOLD_USD"] = AssetInfo(
    code="GOLD_USD", alias="GOLD_USD",
    name="Gold (USD/INR)", category="commodities", default_mean=12.42, default_std=16.60)
_ALL_ASSETS["SILVER_INR_ETF"] = AssetInfo(
    code="SILVER_INR_ETF", alias="SILVER",
    name="Silver INR ETF", category="commodities", default_mean=37.61, default_std=33.83)
_ALL_ASSETS["CRUDE_WTI"] = AssetInfo(
    code="CRUDE_WTI", alias="CRUDE",
    name="Crude Oil WTI", category="commodities", default_mean=10.64, default_std=38.64)
_ALL_ASSETS["USDINR"] = AssetInfo(
    code="USDINR", alias="USDINR",
    name="USD/INR", category="commodities", default_mean=3.58, default_std=7.36)
_ALL_ASSETS["EURINR"] = AssetInfo(
    code="EURINR", alias="EURINR",
    name="EUR/INR", category="commodities", default_mean=3.24, default_std=8.64)
_ALL_ASSETS["GBPINR"] = AssetInfo(
    code="GBPINR", alias="GBPINR",
    name="GBP/INR", category="commodities", default_mean=2.31, default_std=9.23)
_ALL_ASSETS["CRUDE_BRENT"] = AssetInfo(
    code="CRUDE_BRENT", alias="CRUDE_BRENT",
    name="Crude Oil Brent", category="commodities", default_mean=7.10, default_std=37.19)

# ETFs
_ALL_ASSETS["ETF_NIFTY50"] = AssetInfo(
    code="ETF_NIFTY50", alias="NIFTYBEES",
    name="NiftyBees ETF", category="indian_etf", default_mean=15.46, default_std=17.66)
_ALL_ASSETS["ETF_GOLD"] = AssetInfo(
    code="ETF_GOLD", alias="GOLDBEES",
    name="Gold ETF", category="indian_etf", default_mean=14.18, default_std=15.10)
_ALL_ASSETS["ETF_LIQUID"] = AssetInfo(
    code="ETF_LIQUID", alias="LIQUIDBEES",
    name="LiquidBees ETF", category="indian_etf", default_mean=3.08, default_std=0.61)
_ALL_ASSETS["ETF_NIFTYBANK"] = AssetInfo(
    code="ETF_NIFTYBANK", alias="NIPPON_BANK",
    name="BankBees ETF", category="indian_etf", default_mean=20.29, default_std=27.29)
_ALL_ASSETS["ETF_NIFTYIT"] = AssetInfo(
    code="ETF_NIFTYIT", alias="NIPPON_IT",
    name="ITBees ETF", category="indian_etf", default_mean=15.65, default_std=23.58)
_ALL_ASSETS["ETF_GILT_5Y"] = AssetInfo(
    code="ETF_GILT_5Y", alias="GILT_5Y",
    name="Gilt ETF 5Y", category="indian_etf", default_mean=6.28, default_std=2.60)

# Balanced Funds
_ALL_ASSETS["mf_nav_MF_Balanced_SBI_Balanced_Advantage_Fund___"] = AssetInfo(
    code="mf_nav_MF_Balanced_SBI_Balanced_Advantage_Fund___", alias="SBI_BALANCED",
    name="SBI Balanced Advantage Fund", category="indian_balanced", default_mean=11.07, default_std=7.18)
_ALL_ASSETS["mf_nav_MF_Balanced_HDFC_Balanced_Advantage_Fund__"] = AssetInfo(
    code="mf_nav_MF_Balanced_HDFC_Balanced_Advantage_Fund__", alias="HDFC_BALANCED",
    name="HDFC Balanced Advantage Fund", category="indian_balanced", default_mean=15.39, default_std=15.27)
_ALL_ASSETS["mf_nav_MF_FlexiCap_Parag_Parikh_Flexi_Cap_Fund___"] = AssetInfo(
    code="mf_nav_MF_FlexiCap_Parag_Parikh_Flexi_Cap_Fund___", alias="PPFAS_FLEXI",
    name="PPFAS Flexi Cap Fund", category="indian_balanced", default_mean=19.29, default_std=13.06)

# Index Funds
_ALL_ASSETS["mf_nav_MF_IndexFunds_HDFC_Nifty_50_Index_Fund___Dir"] = AssetInfo(
    code="mf_nav_MF_IndexFunds_HDFC_Nifty_50_Index_Fund___Dir", alias="HDFC_NIFTY50",
    name="HDFC Nifty 50 Index Fund", category="indian_equity", default_mean=13.25, default_std=15.79)
_ALL_ASSETS["mf_nav_MF_IndexFunds_ICICI_Prudential_Nifty_50_Inde"] = AssetInfo(
    code="mf_nav_MF_IndexFunds_ICICI_Prudential_Nifty_50_Inde", alias="ICICI_NIFTY50",
    name="ICICI Prudential Nifty 50 Index Fund", category="indian_equity", default_mean=13.26, default_std=15.79)

# Small Cap MFs
_ALL_ASSETS["mf_nav_MF_SmallCap_NIPPON_INDIA_SMALL_CAP_FUND___"] = AssetInfo(
    code="mf_nav_MF_SmallCap_NIPPON_INDIA_SMALL_CAP_FUND___", alias="NIPPON_SMALLCAP",
    name="Nippon India Small Cap Fund", category="indian_equity", default_mean=22.39, default_std=23.22)
_ALL_ASSETS["mf_nav_MF_SmallCap_SBI_Small_Cap_Fund___Direct_Pl"] = AssetInfo(
    code="mf_nav_MF_SmallCap_SBI_Small_Cap_Fund___Direct_Pl", alias="SBI_SMALLCAP",
    name="SBI Small Cap Fund", category="indian_equity", default_mean=26.88, default_std=19.34)
_ALL_ASSETS["mf_nav_MF_SmallCap_Axis_Small_Cap_Fund___Direct_P"] = AssetInfo(
    code="mf_nav_MF_SmallCap_Axis_Small_Cap_Fund___Direct_P", alias="AXIS_SMALLCAP",
    name="Axis Small Cap Fund", category="indian_equity", default_mean=24.62, default_std=17.93)
_ALL_ASSETS["mf_nav_MF_SmallCap_DSP_Small_Cap_Fund___Direct_Pl"] = AssetInfo(
    code="mf_nav_MF_SmallCap_DSP_Small_Cap_Fund___Direct_Pl", alias="DSP_SMALLCAP",
    name="DSP Small Cap Fund", category="indian_equity", default_mean=24.54, default_std=21.39)
_ALL_ASSETS["mf_nav_MF_SmallCap_ICICI_Prudential_Smallcap_Fund"] = AssetInfo(
    code="mf_nav_MF_SmallCap_ICICI_Prudential_Smallcap_Fund", alias="ICICI_SMALLCAP",
    name="ICICI Prudential Smallcap Fund", category="indian_equity", default_mean=19.25, default_std=19.47)

# Large Cap MFs
_ALL_ASSETS["mf_nav_MF_LargeCap_Mirae_Asset_Large_Cap_Fund___D"] = AssetInfo(
    code="mf_nav_MF_LargeCap_Mirae_Asset_Large_Cap_Fund___D", alias="MIRAE_LARGECAP",
    name="Mirae Asset Large Cap Fund", category="indian_equity", default_mean=16.62, default_std=15.78)
_ALL_ASSETS["mf_nav_MF_LargeCap_Tata_Large_Cap_Fund__Direct_Pl"] = AssetInfo(
    code="mf_nav_MF_LargeCap_Tata_Large_Cap_Fund__Direct_Pl", alias="TATA_LARGECAP",
    name="Tata Large Cap Fund", category="indian_equity", default_mean=14.72, default_std=15.78)

# Mid Cap MFs
_ALL_ASSETS["mf_nav_MF_MidCap_ICICI_Prudential_MidCap_Fund__"] = AssetInfo(
    code="mf_nav_MF_MidCap_ICICI_Prudential_MidCap_Fund__", alias="ICICI_MIDCAP",
    name="ICICI Prudential Midcap Fund", category="indian_equity", default_mean=22.10, default_std=19.52)
_ALL_ASSETS["mf_nav_MF_MidCap_Kotak_Midcap_Fund____Direct_Pl"] = AssetInfo(
    code="mf_nav_MF_MidCap_Kotak_Midcap_Fund____Direct_Pl", alias="KOTAK_MIDCAP",
    name="Kotak Midcap Fund", category="indian_equity", default_mean=18.87, default_std=19.62)
_ALL_ASSETS["mf_nav_MF_MidCap_Axis_Midcap_Fund___Direct_Plan"] = AssetInfo(
    code="mf_nav_MF_MidCap_Axis_Midcap_Fund___Direct_Plan", alias="AXIS_MIDCAP",
    name="Axis Midcap Fund", category="indian_equity", default_mean=20.72, default_std=17.25)
_ALL_ASSETS["mf_nav_MF_MidCap_NIPPON_INDIA_BANKING_and_PSU__"] = AssetInfo(
    code="mf_nav_MF_MidCap_NIPPON_INDIA_BANKING_and_PSU__", alias="NIPPON_MIDCAP",
    name="Nippon India Banking & PSU Fund", category="indian_bond", default_mean=7.68, default_std=1.86)

# Sector Funds
_ALL_ASSETS["mf_nav_MF_Sectoral_NIPPON_INDIA_PHARMA_FUND___DIR"] = AssetInfo(
    code="mf_nav_MF_Sectoral_NIPPON_INDIA_PHARMA_FUND___DIR", alias="NIPPON_PHARMA",
    name="Nippon India Pharma Fund", category="indian_equity", default_mean=12.21, default_std=18.38)
_ALL_ASSETS["mf_nav_MF_Sectoral_TATA_Digital_India_Fund_Direct"] = AssetInfo(
    code="mf_nav_MF_Sectoral_TATA_Digital_India_Fund_Direct", alias="TATA_DIGITAL",
    name="Tata Digital India Fund", category="indian_equity", default_mean=17.23, default_std=20.04)


# ── Lookup Functions ─────────────────────────────────────────────────────────

def resolve_asset_code(code_or_alias: str) -> str | None:
    """
    Resolve a user-provided code or alias to the actual data column name.

    Checks in order:
      1. Exact match in _ALL_ASSETS (data column name)
      2. Match in _ALIAS_TO_DATA_CODE (alias)
      3. None
    """
    # Direct match
    if code_or_alias in _ALL_ASSETS:
        return code_or_alias
    # Alias match
    if code_or_alias in _ALIAS_TO_DATA_CODE:
        return _ALIAS_TO_DATA_CODE[code_or_alias]
    return None


def get_asset(code_or_alias: str) -> AssetInfo | None:
    """Get asset info by code or alias."""
    resolved = resolve_asset_code(code_or_alias)
    if resolved:
        return _ALL_ASSETS.get(resolved)
    return None


def get_asset_data_code(code_or_alias: str) -> str | None:
    """Get the actual data column name for a code or alias."""
    return resolve_asset_code(code_or_alias)


def get_asset_name(code_or_alias: str) -> str:
    """Get display name for a code or alias."""
    info = get_asset(code_or_alias)
    if info:
        return info.name
    return code_or_alias


def list_asset_aliases() -> list[str]:
    """List all known aliases."""
    return sorted(_ALIAS_TO_DATA_CODE.keys())


def list_data_codes() -> list[str]:
    """List all actual data column names in the registry."""
    return sorted(_ALL_ASSETS.keys())


def get_all_codes() -> list[str]:
    """List all codes (aliases + data column names)."""
    return sorted(set(_ALIAS_TO_DATA_CODE.keys()) | set(_ALL_ASSETS.keys()))


def list_categories() -> list[str]:
    """List all asset categories."""
    cats = {info.category for info in _ALL_ASSETS.values()}
    return sorted(cats)


def get_assets_by_category(category: str) -> dict[str, AssetInfo]:
    """Get all assets in a category."""
    return {k: v for k, v in _ALL_ASSETS.items() if v.category == category}


def get_default_portfolio_60_40() -> list[tuple[str, float]]:
    """Get default 60/40 portfolio as (alias, allocation) pairs."""
    return [("NIFTY_50", 0.60), ("SBI_GILT", 0.40)]


def resolve_assets(
    assets: list[tuple[str, float]]
) -> list[tuple[str, float]]:
    """
    Resolve a list of (alias_or_code, allocation) tuples to (data_code, allocation).

    Raises ValueError if any asset is not found in data.
    """
    resolved = []
    for code_or_alias, alloc in assets:
        data_code = resolve_asset_code(code_or_alias)
        if data_code is None:
            raise ValueError(
                f"Unknown asset: '{code_or_alias}'. "
                f"Use one of: {sorted(_ALIAS_TO_DATA_CODE.keys())}"
            )
        resolved.append((data_code, alloc))
    return resolved

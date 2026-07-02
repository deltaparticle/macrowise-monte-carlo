"""
Macrowise: Monte Carlo Simulator for Indian Markets

A faithful replica of PortfolioVisualizer.com Monte Carlo simulation engine
adapted for Indian market data, tax rules, and investment conventions.
"""

from macrowise.engine.monte_carlo import MonteCarloConfig, MonteCarloSimulation
from macrowise.engine.cashflow import CashFlowConfig
from macrowise.engine.tax import IndianTaxCalculator, IndianTaxRates, DEFAULT_TAX_RATES
from macrowise.data.asset_registry import (
    get_asset,
    get_asset_name,
    list_asset_aliases,
    list_categories,
    get_default_portfolio_60_40,
    PV_TO_INDIAN_ALIAS,
    resolve_assets,
)
from macrowise.viz.charts import (
    plot_allocation_pie,
    plot_balance_chart,
    plot_terminal_distribution,
    plot_drawdown_distribution,
    format_inr,
)

__version__ = "1.0.0"
__author__ = "Macrowise Team"
__description__ = "Monte Carlo simulation for Indian investors"

__all__ = [
    "MonteCarloConfig",
    "MonteCarloSimulation",
    "CashFlowConfig",
    "IndianTaxCalculator",
    "IndianTaxRates",
    "DEFAULT_TAX_RATES",
    "get_asset",
    "get_asset_name",
    "list_asset_aliases",
    "list_categories",
    "get_default_portfolio_60_40",
    "PV_TO_INDIAN_ALIAS",
    "resolve_assets",
    "plot_allocation_pie",
    "plot_balance_chart",
    "plot_terminal_distribution",
    "plot_drawdown_distribution",
    "format_inr",
]


def MonteCarlo(config: MonteCarloConfig) -> MonteCarloSimulation:
    """Create and run a Monte Carlo simulation."""
    return MonteCarloSimulation(config)

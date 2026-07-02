"""
Python API for Monte Carlo simulation.

Usage:
    from macrowise import MonteCarlo, CashFlowConfig, MonteCarloConfig

    config = MonteCarloConfig(
        initial_balance=10_00_000,
        years=30,
        assets=[("NIFTY_50_TRI", 0.60), ("BOND_SBI_GILT", 0.40)],
        cashflow=CashFlowConfig(
            adjustment_type=2,
            amount=-50_000,      # ₹50,000/month withdrawal
            frequency="monthly",
            inflation_adjusted=True,
        ),
        model=1,  # Historical bootstrap
        simulations=10_000,
    )

    sim = MonteCarlo(config)
    results = sim.run()

    print(results.median_cagr)
    print(results.performance_summary)
"""

from macrowise.engine.monte_carlo import MonteCarloConfig, MonteCarloSimulation
from macrowise.engine.cashflow import CashFlowConfig
from macrowise.engine.tax import IndianTaxCalculator, IndianTaxRates, DEFAULT_TAX_RATES
from macrowise.data.asset_registry import (
    get_asset,
    list_data_codes,
    get_default_portfolio_60_40,
    PV_TO_INDIAN_ALIAS,
)
from macrowise.viz.charts import (
    plot_allocation_pie,
    plot_balance_chart,
    plot_terminal_distribution,
    plot_drawdown_distribution,
    format_inr,
)

__all__ = [
    "MonteCarlo",
    "MonteCarloConfig",
    "CashFlowConfig",
    "IndianTaxCalculator",
    "IndianTaxRates",
    "MonteCarloSimulation",
    "MonteCarloResults",
    "plot_allocation_pie",
    "plot_balance_chart",
    "plot_terminal_distribution",
    "plot_drawdown_distribution",
    "format_inr",
    "get_asset",
    "list_data_codes",
    "get_default_portfolio_60_40",
    "PV_TO_INDIAN_ALIAS",
]


def MonteCarlo(config: MonteCarloConfig) -> MonteCarloSimulation:
    """Create and run a Monte Carlo simulation."""
    return MonteCarloSimulation(config)

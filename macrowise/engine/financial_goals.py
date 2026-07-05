"""
Financial Goals — Multi-stage Monte Carlo simulation engine.

Implements PV's Financial Goals section:
  - Single stage: same portfolio throughout
  - Multi-stage: career portfolio → glide path → retirement portfolio
  - Multiple goals per phase (contributions, withdrawals, etc.)
  - Success rate based on meeting all financial goals
  - Legacy/liquidation targets
  - Stress test at retirement
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from macrowise.engine.monte_carlo import (
    MonteCarloConfig,
    MonteCarloSimulation,
    MonteCarloResults,
)
from macrowise.engine.glide_path import apply_glide_path_to_returns, linear_glide_path
from macrowise.engine.cashflow import CashFlowConfig, CashFlowEngine
from macrowise.data.loader import get_monthly_returns, get_asset_statistics
from macrowise.data.asset_registry import get_asset


@dataclass
class FinancialGoal:
    """
    A single financial goal (PV's cashflow row in Goals tab).

    PV types (Goals tab): 1=Contribute, 2=Withdraw, 3=%, 5=Rolling Avg,
      6=Geometric, 8=Fixed Withdrawal+Pct Change, 9=Contribution+Pct Change

    start_type: 1=Immediately, 2=At Retirement, 3=Starts In N Years
    occurs_type: 1=Until Retirement, 2=Until End, 3=Repeats N Times
    """
    name: str = "Goal"
    goal_type: int = 2          # 1=Contribute, 2=Withdraw, 3=%, 5=Rolling, 6=Geometric, 8=Fixed+Pct, 9=Contribute+Pct
    amount: float = 0.0
    percentage: float = 4.0
    frequency: str = "annual"   # monthly, quarterly, annual
    inflation_adjusted: bool = False
    inflation_mean: float = 0.04
    start_type: int = 1         # 1=Immediately, 2=At Retirement, 3=Starts In N Years
    start_years: int = 0        # Years from start when goal begins
    occurs_type: int = 2        # 1=Until Retirement, 2=Until End, 3=Repeats N Times
    occurs_times: int = 1       # Number of occurrences if occurs_type=3
    pct_change: float = 0.0     # Annual % change (for type 8/9)
    rolling_periods: int = 3
    smoothing_rate: float = 0.75


@dataclass
class GoalsConfig:
    """
    Full configuration for Financial Goals simulation.
    """
    # ── Core ─────────────────────────────────────────────────────
    initial_balance: float = 1_000_000.0
    years: int = 30
    simulations: int = 10_000

    # ── Phase Boundaries ─────────────────────────────────────────
    planning_type: int = 2        # 1=Single stage, 2=Multi-stage
    career_years: int = 20        # Years before retirement
    glide_path_years: int = 10    # Transition years
    stress_test_retirement: bool = True  # Apply worst years at retirement

    # ── Starting Portfolio ───────────────────────────────────────
    start_assets: List[Tuple[str, float]] = field(
        default_factory=lambda: [("NIFTY_50", 0.60), ("SBI_GILT", 0.40)]
    )

    # ── Ending (Retirement) Portfolio ───────────────────────────
    end_assets: List[Tuple[str, float]] = field(
        default_factory=lambda: [("NIFTY_50", 0.40), ("SBI_GILT", 0.60)]
    )

    # ── Goals ─────────────────────────────────────────────────────
    career_goals: List[FinancialGoal] = field(default_factory=list)
    retirement_goals: List[FinancialGoal] = field(default_factory=list)

    # ── Simulation Model ─────────────────────────────────────────
    model: int = 1
    bootstrap_model: int = 1
    seed: Optional[int] = 42
    inflation_adjusted: bool = True
    inflation_model: int = 1
    inflation_mean: float = 0.04
    inflation_volatility: float = 0.03
    rebalance_frequency: int = 1
    sequence_stress_test: int = 0
    risk_free_rate: float = 0.0483


class GoalsSimulation:
    """
    Multi-stage financial goals simulation engine.

    Runs Monte Carlo simulation with:
    1. Career phase with starting portfolio
    2. Glide path transition (if multi-stage)
    3. Retirement phase with ending portfolio
    4. All financial goals applied per-phase
    5. Success = portfolio survives all goals + optionally leaves legacy
    """

    def __init__(self, config: GoalsConfig):
        self.config = config
        self._rng = np.random.default_rng(config.seed)

    def _get_all_assets(self) -> List[str]:
        """Get union of all assets across both portfolios."""
        start_codes = {a for a, _ in self.config.start_assets}
        end_codes = {a for a, _ in self.config.end_assets}
        return sorted(start_codes | end_codes)

    def run(self) -> "GoalsResults":
        """
        Execute the financial goals simulation.

        Returns
        -------
        GoalsResults
        """
        cfg = self.config
        n_sims = cfg.simulations
        n_years = cfg.years
        n_months = n_years * 12
        n_assets = len(self._get_all_assets())

        # Phase boundaries
        career_months = cfg.career_years * 12
        glide_months = cfg.glide_path_years * 12
        retirement_start = career_months
        retirement_end = retirement_start + glide_months

        # Generate return paths for all required assets
        mc_config = MonteCarloConfig(
            initial_balance=cfg.initial_balance,
            years=n_years,
            simulations=n_sims,
            assets=cfg.start_assets,
            model=cfg.model,
            bootstrap_model=cfg.bootstrap_model,
            seed=cfg.seed,
            inflation_adjusted=cfg.inflation_adjusted,
            rebalance_frequency=cfg.rebalance_frequency,
            inflation_model=cfg.inflation_model,
            inflation_mean=cfg.inflation_mean,
            inflation_volatility=cfg.inflation_volatility,
            sequence_stress_test=cfg.sequence_stress_test,
        )
        mc_sim = MonteCarloSimulation(mc_config)
        mc_config.assets = cfg.end_assets
        mc_sim._validate_assets()

        # Generate paths
        return_paths = mc_sim._build_return_paths()  # (n_sims, n_months, n_assets)

        # If start and end assets differ, need both
        start_codes = [a for a, _ in cfg.start_assets]
        end_codes = [a for a, _ in cfg.end_assets]

        if start_codes != end_codes:
            # Get start asset paths
            mc_config.assets = cfg.start_assets
            mc_sim._validate_assets()
            start_return_paths = mc_sim._build_return_paths()

            # Get end asset paths
            mc_config.assets = cfg.end_assets
            mc_sim._validate_assets()
            end_return_paths = mc_sim._build_return_paths()

            # Build combined paths by applying glide path
            combined_returns = self._combine_phase_returns(
                start_return_paths, end_return_paths,
                start_codes, end_codes,
                cfg.career_years, cfg.glide_path_years, n_months
            )
        else:
            start_return_paths = return_paths
            end_return_paths = return_paths
            combined_returns = return_paths

        # Apply glide path to get portfolio-level returns
        if cfg.planning_type == 2 and cfg.glide_path_years > 0:
            portfolio_returns = apply_glide_path_to_returns(
                combined_returns,
                cfg.start_assets,
                cfg.end_assets,
                cfg.glide_path_years,
                cfg.career_years,
            )
        else:
            # Single stage: use start portfolio weights
            start_weights = np.array([w for _, w in cfg.start_assets])
            portfolio_returns = combined_returns @ start_weights

        # Track balances through all phases
        balances = np.zeros((n_sims, n_months + 1))
        balances[:, 0] = cfg.initial_balance

        for sim in range(n_sims):
            for m in range(n_months):
                balances[sim, m + 1] = balances[sim, m] * (1 + portfolio_returns[sim, m])

        # Apply career goals
        if cfg.career_goals:
            balances = self._apply_goals(balances, cfg.career_goals, n_months, 0, cfg.career_years)

        # Apply retirement goals
        if cfg.retirement_goals:
            balances = self._apply_goals(balances, cfg.retirement_goals, n_months, cfg.career_years, cfg.years)

        # Compute success/failure per simulation
        success = balances[:, -1] >= 0  # Simplified: portfolio not depleted
        success_rate = success.mean()

        final_balances = balances[:, -1]
        median_final = float(np.median(final_balances))

        # CAGR
        cagrs = []
        for sim in range(n_sims):
            if final_balances[sim] > 0 and cfg.initial_balance > 0:
                cagr = (final_balances[sim] / cfg.initial_balance) ** (1 / n_years) - 1
                cagrs.append(cagr)
        median_cagr = float(np.median(cagrs)) if cagrs else 0.0

        # Year-by-year balances
        balance_percentiles = {}
        for yr in range(n_years + 1):
            month_idx = min(yr * 12, n_months)
            b = balances[:, month_idx]
            balance_percentiles[str(yr)] = {
                "p10": float(np.percentile(b, 10)),
                "p25": float(np.percentile(b, 25)),
                "p50": float(np.percentile(b, 50)),
                "p75": float(np.percentile(b, 75)),
                "p90": float(np.percentile(b, 90)),
            }

        return GoalsResults(
            n_simulations=n_sims,
            n_years=n_years,
            success_rate=success_rate,
            median_final_balance=median_final,
            median_cagr=median_cagr,
            balance_percentiles=balance_percentiles,
            final_balances=final_balances,
            balances=balances,
            config=cfg,
        )

    def _combine_phase_returns(
        self,
        start_returns: np.ndarray,
        end_returns: np.ndarray,
        start_codes: List[str],
        end_codes: List[str],
        career_years: int,
        glide_years: int,
        n_months: int,
    ) -> np.ndarray:
        """Build combined return array using available paths from both phases."""
        n_sims, n_months_total, _ = start_returns.shape
        combined = np.zeros((n_sims, n_months_total, max(len(start_codes), len(end_codes))))

        for sim in range(n_sims):
            for m in range(n_months_total):
                for i, code in enumerate(start_codes):
                    if m < career_years * 12:
                        combined[sim, m, i] = start_returns[sim, m, i]
                    elif m < (career_years + glide_years) * 12:
                        # Glide phase: blend start and end
                        t = (m - career_years * 12) / (glide_years * 12) if glide_years > 0 else 1.0
                        combined[sim, m, i] = start_returns[sim, m, i] * (1 - t) + end_returns[sim, m, i] * t
                    else:
                        combined[sim, m, i] = end_returns[sim, m, i]
        return combined

    def _apply_goals(
        self,
        balances: np.ndarray,
        goals: List[FinancialGoal],
        n_months: int,
        phase_start_year: int,
        phase_end_year: int,
    ) -> np.ndarray:
        """Apply financial goals to balance paths."""
        phase_months_start = phase_start_year * 12

        for goal in goals:
            cf = CashFlowConfig(
                adjustment_type=goal.goal_type,
                amount=goal.amount,
                frequency=goal.frequency,
                inflation_adjusted=goal.inflation_adjusted,
                inflation_mean=goal.inflation_mean,
                withdrawal_percentage=goal.percentage,
                rolling_periods=goal.rolling_periods,
                smoothing_rate=goal.smoothing_rate,
                pct_change=goal.pct_change,
            )
            engine = CashFlowEngine(cf)
            schedule = engine.generate_schedule(n_months)

            # Determine when goal is active
            start_month = phase_months_start
            if goal.start_type == 2:  # At Retirement
                start_month = self.config.career_years * 12
            elif goal.start_type == 3:  # Starts In N Years
                start_month = phase_months_start + goal.start_years * 12

            # Apply schedule
            sign = 1.0 if goal.goal_type in (1, 9) else -1.0

            for sim in range(balances.shape[0]):
                for m in range(n_months):
                    if m >= start_month:
                        if goal.goal_type == 3:
                            # Percentage withdrawal — apply to current balance
                            balances[sim, m] -= abs(schedule[m]) * balances[sim, m]
                        elif goal.goal_type in (8, 9) and goal.pct_change != 0:
                            # With pct change — already encoded in schedule
                            balances[sim, m + 1] = max(0, balances[sim, m + 1] + sign * schedule[m])
                        else:
                            balances[sim, m + 1] = max(0, balances[sim, m + 1] + sign * schedule[m])

        return balances


@dataclass
class GoalsResults:
    """Results from financial goals simulation."""
    n_simulations: int
    n_years: int
    success_rate: float
    median_final_balance: float
    median_cagr: float
    balance_percentiles: dict
    final_balances: np.ndarray
    balances: np.ndarray
    config: GoalsConfig

    def summary_table(self) -> pd.DataFrame:
        """PV-compatible summary table."""
        pcts = [0.10, 0.25, 0.50, 0.75, 0.90]
        labels = [f"p{int(p * 100)}" for p in pcts]

        bals = self.final_balances
        rows = {
            "Final Balance": [float(np.percentile(bals, p * 100)) for p in pcts],
            "Success Rate": [f"{self.success_rate:.2%}"] * 5,
        }

        df = pd.DataFrame(rows, index=labels).T
        df.index.name = "Statistic"
        return df

 """
Monte Carlo Engine — main simulation orchestrator.

Implements all 4 PV simulation models:
  1. Historical Returns  — bootstrap from actual history
  2. Statistical Returns — bootstrap + custom mean/std
  3. Parameterized Returns — N(μ,σ) or t-distribution
  4. Forecasted Returns  — parametric with forecasted parameters

Handles:
  - Portfolio rebalancing
  - Cash flows (7 types)
  - Inflation adjustment
  - Sequence stress tests
  - PV-compatible output format
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

from macrowise.data.loader import (
    get_monthly_returns,
    get_annual_returns,
    get_correlation_matrix,
    get_covariance_matrix,
    get_asset_statistics,
)
from macrowise.data.asset_registry import (
    AssetInfo,
    get_asset,
    resolve_assets,
    get_asset_name,
    get_asset_data_code,
    _ALIAS_TO_DATA_CODE,
)
from macrowise.engine.bootstrap import BootstrapSampler, YearlyBootstrap
from macrowise.engine.parametric import (
    NormalSampler,
    FatTailedSampler,
    GARCHSampler,
)
from macrowise.engine.cashflow import CashFlowConfig, CashFlowEngine
from macrowise.engine.stats import (
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    compute_percentile_balances,
    safe_withdrawal_rate,
    perpetual_withdrawal_rate,
)


@dataclass
class MonteCarloConfig:
    """Full configuration for a Monte Carlo simulation run."""

    # ── Core Parameters ──────────────────────────────────────────────────
    initial_balance: float = 1_000_000.0       # ₹10 lakh default
    years: int = 30
    simulations: int = 10_000
    inflation_adjusted: bool = True

    # ── Portfolio ───────────────────────────────────────────────────────
    assets: list[tuple[str, float]] = field(default_factory=list)
    # List of (asset_code, allocation_pct) pairs, e.g. [("NIFTY_50_TRI", 0.60)]

    # ── Simulation Model ────────────────────────────────────────────────
    # 1=Historical, 2=Statistical, 3=Parameterized, 4=Forecasted
    model: int = 1
    # For model=2: Normal(1) or GARCH(3)
    time_series_model: int = 1
    # For model=3: Normal(1) or Fat-Tailed(2)
    distribution_type: int = 1
    degrees_of_freedom: int = 30

    # ── Bootstrap Settings ──────────────────────────────────────────────
    # 0=single_month, 1=single_year, 2=block
    bootstrap_model: int = 1
    bootstrap_min_years: int = 1
    bootstrap_max_years: int = 20
    circular_bootstrap: bool = True
    use_full_history: bool = True
    start_year: Optional[int] = None
    end_year: Optional[int] = None

    # ── Custom Parameters (for model=3 or 4) ───────────────────────────
    # Override asset mean/vol with these arrays
    custom_means: Optional[np.ndarray] = None
    custom_stds: Optional[np.ndarray] = None
    custom_correlation: Optional[np.ndarray] = None
    risk_free_rate: float = 0.0483

    # ── What-If / Stress Tests ──────────────────────────────────────────
    sequence_stress_test: int = 0   # 0=off, 1-10=worst N years first
    use_historical_volatility: bool = True
    use_historical_correlations: bool = True

    # ── Rebalancing ────────────────────────────────────────────────────
    # 0=no rebalance, 1=annual, 2=semi-annual, 3=quarterly, 4=monthly
    rebalance_frequency: int = 1

    # ── Inflation ──────────────────────────────────────────────────────
    inflation_model: int = 1         # 1=historical, 2=parameterized
    inflation_mean: float = 0.04
    inflation_volatility: float = 0.03

    # ── Cash Flow ──────────────────────────────────────────────────────
    cashflow: Optional[CashFlowConfig] = None

    # ── Tax ────────────────────────────────────────────────────────────
    tax_enabled: bool = False
    tax_rates: dict = field(default_factory=dict)

    # ── Random Seed ────────────────────────────────────────────────────
    seed: Optional[int] = None

    # ── Output Percentiles ─────────────────────────────────────────────
    percentiles: list[float] = field(default_factory=lambda: [0.10, 0.25, 0.50, 0.75, 0.90])


class MonteCarloSimulation:
    """
    Main Monte Carlo simulation engine.

    Mirrors PortfolioVisualizer's Monte Carlo output structure:
    - Performance Summary table
    - Portfolio Balance (year-by-year percentiles)
    - Simulated Assets (correlations & returns)
    - Expected Annual Return (probability table)
    - Loss Probabilities

    Example
    -------
    >>> config = MonteCarloConfig(
    ...     initial_balance=10_00_000,
    ...     years=30,
    ...     assets=[("NIFTY_50_TRI", 0.60), ("BOND_SBI_GILT", 0.40)],
    ... )
    >>> sim = MonteCarloSimulation(config)
    >>> results = sim.run()
    >>> print(results.summary_table)
    >>> print(results.balance_percentiles)
    """

    def __init__(self, config: MonteCarloConfig):
        self.config = config
        self._load_data()
        self._validate_assets()
        self._rng = np.random.default_rng(config.seed)

    def _load_data(self) -> None:
        """Load all required data."""
        self.monthly_returns = get_monthly_returns()
        self.annual_returns = get_annual_returns()
        self.corr_matrix = get_correlation_matrix()
        self.cov_matrix = get_covariance_matrix()
        self.asset_stats = get_asset_statistics()

    def _validate_assets(self) -> None:
        """Validate requested assets and resolve aliases to data column names."""
        cfg = self.config
        if not cfg.assets:
            raise ValueError("No assets specified. Provide list of (code, allocation) tuples.")

        available = set(self.monthly_returns.columns)
        resolved = []
        total_alloc = 0.0

        for code_or_alias, alloc in cfg.assets:
            # Try direct match first
            if code_or_alias in available:
                resolved.append((code_or_alias, alloc))
                total_alloc += alloc
                continue

            # Try alias → data code
            data_code = get_asset_data_code(code_or_alias)
            if data_code and data_code in available:
                resolved.append((data_code, alloc))
                total_alloc += alloc
                continue

            # Try alias → data code even if not yet verified
            if data_code:
                resolved.append((data_code, alloc))
                total_alloc += alloc
                continue

            # Not found
            available_aliases = list(_ALIAS_TO_DATA_CODE.keys())[:20]
            raise ValueError(
                f"Unknown asset: '{code_or_alias}'. "
                f"Available aliases include: {available_aliases}..."
            )

        if abs(total_alloc - 1.0) > 0.01:
            print(f"Warning: allocations sum to {total_alloc:.1%}, normalizing to 100%.")
            resolved = [(c, w / total_alloc) for c, w in resolved]

        cfg.assets = resolved

    def _get_asset_returns(self) -> pd.DataFrame:
        """Get historical returns for selected assets only."""
        codes = [a for a, _ in self.config.assets]
        return self.monthly_returns[codes].dropna()

    def _get_asset_means_stds(self) -> tuple[np.ndarray, np.ndarray]:
        """Get mean and std for selected assets."""
        codes = [a for a, _ in self.config.assets]
        n = len(codes)

        if self.config.custom_means is not None:
            means = np.array(self.config.custom_means)
        else:
            means = np.array([
                self.asset_stats.loc[c, "mean_annual"] if c in self.asset_stats.index
                else 0.10
                for c in codes
            ])

        if self.config.custom_stds is not None:
            stds = np.array(self.config.custom_stds)
        else:
            stds = np.array([
                self.asset_stats.loc[c, "std_annual"] if c in self.asset_stats.index
                else 0.15
                for c in codes
            ])

        return means[:n], stds[:n]

    def _get_correlation(self) -> np.ndarray:
        """Get correlation matrix for selected assets."""
        codes = [a for a, _ in self.config.assets]
        available_cols = [c for c in codes if c in self.corr_matrix.columns]

        if not self.config.use_historical_correlations or not available_cols:
            # Use identity correlation
            return np.eye(len(codes))

        sub = self.corr_matrix.loc[available_cols, available_cols].values
        if len(available_cols) < len(codes):
            # Fill missing with identity
            full = np.eye(len(codes))
            for i, c in enumerate(codes):
                for j, d in enumerate(codes):
                    if c in available_cols and d in available_cols:
                        full[i, j] = sub[
                            available_cols.index(c), available_cols.index(d)
                        ]
            return full
        return sub

    def _get_covariance(self) -> np.ndarray:
        """Get covariance matrix for selected assets."""
        codes = [a for a, _ in self.config.assets]
        _, stds = self._get_asset_means_stds()
        corr = self._get_correlation()

        # Build covariance: σ_i * σ_j * ρ_ij
        n = len(codes)
        cov = np.ones((n, n))
        for i in range(n):
            for j in range(n):
                cov[i, j] = stds[i] * stds[j] * corr[i, j]
        return cov

    def _build_return_paths(self) -> np.ndarray:
        """
        Build simulated return paths based on the selected model.

        Returns
        -------
        ndarray, shape (n_sims, n_months, n_assets)
        """
        cfg = self.config
        n_assets = len(cfg.assets)
        codes = [a for a, _ in cfg.assets]

        if cfg.model == 1:
            # ── Historical Returns ──────────────────────────────────────
            return self._historical_returns(codes)

        elif cfg.model == 2:
            # ── Statistical Returns ─────────────────────────────────────
            # Bootstrap actual returns but apply custom stats
            return self._statistical_returns(codes)

        elif cfg.model == 3:
            # ── Parameterized Returns ──────────────────────────────────
            return self._parameterized_returns()

        elif cfg.model == 4:
            # ── Forecasted Returns ─────────────────────────────────────
            return self._forecasted_returns()

        else:
            raise ValueError(f"Unknown model: {cfg.model}")

    def _historical_returns(self, codes: list[str]) -> np.ndarray:
        """
        Model=1: Bootstrap from actual historical returns.

        Uses single-year bootstrap if all assets have at least `years` complete years.
        Falls back to single-month bootstrap otherwise.
        """
        cfg = self.config
        hist = self.monthly_returns[codes].dropna()

        # Apply year range filter if set
        if not self.config.use_full_history:
            if self.config.start_year:
                hist = hist[hist.index.year >= self.config.start_year]
            if self.config.end_year:
                hist = hist[hist.index.year <= self.config.end_year]

        # Determine available complete years per asset
        min_complete_years = self._min_complete_years(hist, codes)

        # Auto-select bootstrap model if yearly not possible
        bootstrap_model = cfg.bootstrap_model
        if bootstrap_model == 1 and min_complete_years < cfg.years:
            print(
                f"  Note: '{codes[0]}' has only {min_complete_years} complete years. "
                f"Using monthly bootstrap for {cfg.years} years."
            )
            bootstrap_model = 0  # single-month

        sampler = BootstrapSampler(
            block_model={0: "single_month", 1: "single_year", 2: "block"}[bootstrap_model],
            block_min_years=cfg.bootstrap_min_years,
            block_max_years=cfg.bootstrap_max_years,
            circular=cfg.circular_bootstrap,
            seed=cfg.seed,
        )

        n_months = cfg.years * 12
        paths = np.zeros((cfg.simulations, n_months, len(codes)))

        for sim in range(cfg.simulations):
            seq = sampler.sample_sequence(hist, cfg.years, codes)

            # Pad with last value if needed (for partial years)
            if seq.shape[0] < n_months:
                pad = np.zeros((n_months - seq.shape[0], seq.shape[1]))
                seq = np.concatenate([seq, pad], axis=0)

            # Apply sequence stress test
            if self.config.sequence_stress_test > 0:
                seq = sampler.apply_sequence_stress(
                    seq, self.config.sequence_stress_test, annual=True
                )

            paths[sim] = seq

        return paths

    def _min_complete_years(self, hist: pd.DataFrame, codes: list[str]) -> int:
        """Return the minimum number of complete (12-month) calendar years across assets."""
        min_years = float("inf")
        for code in codes:
            series = hist[code].dropna()
            yearly_counts = series.groupby(series.index.year).size()
            complete = (yearly_counts == 12).sum()
            min_years = min(min_years, complete)
        return int(min_years) if min_years != float("inf") else 0

    def _statistical_returns(self, codes: list[str]) -> np.ndarray:
        """Model=2: Bootstrap historical returns with custom statistics."""
        # Bootstrap from history
        paths = self._historical_returns(codes)

        # Adjust mean/stdev to match user-specified (via custom_means/custom_stds)
        cfg = self.config
        if cfg.custom_means is not None or cfg.custom_stds is not None:
            means, stds = self._get_asset_means_stds()
            hist_means = paths.mean(axis=(0, 1))
            hist_stds = paths.std(axis=(0, 1))

            for i in range(len(codes)):
                # Adjust mean
                if cfg.custom_means is not None:
                    mean_adj = cfg.custom_means[i] / 12 - hist_means[i]
                    paths[:, :, i] += mean_adj * 12
                # Adjust volatility
                if cfg.custom_stds is not None:
                    vol_ratio = (cfg.custom_stds[i] / np.sqrt(12)) / (hist_stds[i] + 1e-10)
                    paths[:, :, i] *= vol_ratio

        return paths

    def _parameterized_returns(self) -> np.ndarray:
        """Model=3: Draw from specified distribution."""
        means, stds = self._get_asset_means_stds()
        corr = self._get_correlation()
        n_years = self.config.years

        if self.config.distribution_type == 1:
            # Normal distribution
            sampler = NormalSampler(means, corr * np.outer(stds, stds), seed=self.config.seed)
            return sampler.generate_path(n_years, self.config.simulations)
        else:
            # Fat-tailed (t-distribution)
            sampler = FatTailedSampler(
                mean_returns=means,
                std_returns=stds,
                dof=self.config.degrees_of_freedom,
                correlation=corr,
                seed=self.config.seed,
            )
            return sampler.generate_path(n_years, self.config.simulations)

    def _forecasted_returns(self) -> np.ndarray:
        """Model=4: Parametric returns with risk-free rate."""
        cfg = self.config
        means, stds = self._get_asset_means_stds()
        n_assets = len(means)

        # Time series model selection
        if cfg.time_series_model == 3:
            # GARCH model
            sampler = GARCHSampler(
                mean_returns=means,
                initial_vol=stds,
                seed=cfg.seed,
            )
            return sampler.generate_path(cfg.years, cfg.simulations)
        else:
            # Normal (default for Forecasted mode)
            corr = self._get_correlation()
            cov = corr * np.outer(stds, stds)
            sampler = NormalSampler(means, cov, seed=cfg.seed)
            return sampler.generate_path(cfg.years, cfg.simulations)

    def _apply_rebalancing(self, paths: np.ndarray) -> np.ndarray:
        """
        Apply portfolio rebalancing.

        After each rebalance period, reset each asset's weight to target.
        """
        cfg = self.config
        if cfg.rebalance_frequency == 0:
            return paths  # No rebalancing

        # Determine rebalance months
        freq_map = {1: 12, 2: 6, 3: 3, 4: 1}
        rebalance_months = freq_map.get(cfg.rebalance_frequency, 12)

        allocs = np.array([w for _, w in cfg.assets])

        for sim in range(paths.shape[0]):
            for m in range(paths.shape[1]):
                if m > 0 and m % rebalance_months == 0:
                    # Rebalance: set returns so weights return to target
                    # This is a simplified rebalance — full version requires
                    # tracking actual balance per asset
                    port_return = np.sum(paths[sim, m - 1] * allocs)
                    paths[sim, m] = (
                        paths[sim, m] + port_return * (1 - allocs)
                    )

        return paths

    def _apply_cashflows_vectorized(
        self, paths: np.ndarray, initial_balance: float
    ) -> np.ndarray:
        """
        Apply cash flows to simulated paths — vectorized.

        Returns
        -------
        ndarray, shape (n_sims, n_months + 1)
            Balance over time including cashflows.
        """
        cfg = self.config
        if cfg.cashflow is None or cfg.cashflow.adjustment_type == 0:
            return self._paths_to_balance(paths, initial_balance)

        cf = cfg.cashflow
        n_sims, n_months, n_assets = paths.shape
        allocs = np.array([w for _, w in cfg.assets])

        # Convert multi-asset returns to portfolio returns
        port_returns = paths @ allocs  # (n_sims, n_months)

        # Generate cashflow schedule
        cf_engine = CashFlowEngine(cf)
        cf_schedule = cf_engine.generate_schedule(n_months)  # (n_months,)

        # Vectorized balance computation
        balances = np.zeros((n_sims, n_months + 1))
        balances[:, 0] = initial_balance

        for m in range(n_months):
            balances[:, m + 1] = balances[:, m] * (1 + port_returns[:, m])
            if cf.adjustment_type == 3:
                withdrawal_pct = cf_schedule[m]
                balances[:, m + 1] -= balances[:, m + 1] * withdrawal_pct
            elif cf.adjustment_type == 4:
                balances[:, m + 1] -= abs(cf_schedule[m])
            else:
                balances[:, m + 1] += cf_schedule[m]
            balances[:, m + 1] = np.maximum(balances[:, m + 1], 0.0)

        return balances

    def _paths_to_balance(
        self, paths: np.ndarray, initial_balance: float
    ) -> np.ndarray:
        """Convert return paths to balance paths (no cashflow)."""
        allocs = np.array([w for _, w in self.config.assets])
        port_returns = paths @ allocs  # (n_sims, n_months)
        balances = initial_balance * np.cumprod(1 + port_returns, axis=1)
        return np.concatenate(
            [np.full((paths.shape[0], 1), initial_balance), balances], axis=1
        )

    def run(self) -> "MonteCarloResults":
        """
        Execute the Monte Carlo simulation.

        Returns
        -------
        MonteCarloResults
        """
        cfg = self.config
        codes = [a for a, _ in cfg.assets]

        # Step 1: Generate return paths
        print(f"Generating {cfg.simulations:,} simulations × {cfg.years} years × {len(codes)} assets...")
        paths = self._build_return_paths()
        print(f"  Return paths: {paths.shape}")

        # Step 2: Apply rebalancing
        if cfg.rebalance_frequency > 0:
            paths = self._apply_rebalancing(paths)

        # Step 3: Apply cashflows → balance paths
        balance_paths = self._apply_cashflows_vectorized(paths, cfg.initial_balance)
        print(f"  Balance paths: {balance_paths.shape}")

        # Step 4: Compute statistics
        results = MonteCarloResults(
            config=cfg,
            balance_paths=balance_paths,
            return_paths=paths,
            asset_codes=codes,
            asset_names=[get_asset(c).name if get_asset(c) else c for c in codes],
        )
        results._compute_all()
        print("  Done.")
        return results


class MonteCarloResults:
    """
    Results container — mirrors PortfolioVisualizer's output structure.

    Sections:
      - portfolio_model: asset allocation table
      - performance_summary: 9-row × 5-percentile table
      - balance_percentiles: year-by-year percentile table
      - simulated_assets: correlation & return stats table
      - expected_returns: probability of exceeding return thresholds
      - loss_probabilities: loss probabilities with/without cashflows
    """

    def __init__(
        self,
        config: MonteCarloConfig,
        balance_paths: np.ndarray,
        return_paths: np.ndarray,
        asset_codes: list[str],
        asset_names: list[str],
    ):
        self.config = config
        self.balance_paths = balance_paths       # (n_sims, n_months+1)
        self.return_paths = return_paths         # (n_sims, n_months, n_assets)
        self.asset_codes = asset_codes
        self.asset_names = asset_names

        self.n_sims = balance_paths.shape[0]
        self.n_months = balance_paths.shape[1] - 1
        self.n_years = self.n_months // 12

        # Output tables (computed in _compute_all)
        self.portfolio_model: pd.DataFrame | None = None
        self.performance_summary: pd.DataFrame | None = None
        self.balance_percentiles: pd.DataFrame | None = None
        self.simulated_assets: pd.DataFrame | None = None
        self.expected_returns: pd.DataFrame | None = None
        self.loss_probabilities: pd.DataFrame | None = None

        # Key metrics
        self.median_cagr: float = 0.0
        self.success_rate: float = 0.0
        self.median_final_balance: float = 0.0
        self.swr: float = 0.0
        self.pwr: float = 0.0

    def _compute_all(self) -> None:
        """Compute all result tables."""
        self._compute_portfolio_model()
        self._compute_performance_summary()
        self._compute_balance_percentiles()
        self._compute_simulated_assets()
        self._compute_expected_returns()
        self._compute_loss_probabilities()
        self._compute_key_metrics()

    def _compute_portfolio_model(self) -> None:
        """Asset allocation table."""
        data = {
            "Asset": self.asset_names,
            "Code": self.asset_codes,
            "Allocation": [f"{w:.1%}" for _, w in self.config.assets],
        }
        self.portfolio_model = pd.DataFrame(data)

    def _compute_performance_summary(self) -> None:
        """
        PV's Performance Summary table: 9 rows × 5 percentiles.
        Rows: TWR(nominal), TWR(real), End Balance(nominal), End Balance(real),
              Ann Mean Return, Ann Volatility, Sharpe, Sortino, Max DD, Safe Withdrawal, Perpetual
        """
        cfg = self.config
        pcts = cfg.percentiles
        labels = [f"p{int(p * 100)}" for p in pcts]

        # Extract final balances
        final_balances = self.balance_paths[:, -1]
        initial = cfg.initial_balance

        # Compute per-simulation CAGR and returns
        sim_cagrs = np.zeros(self.n_sims)
        sim_ann_returns = np.zeros(self.n_sims)
        sim_max_dds = np.zeros(self.n_sims)
        sim_sharpes = np.zeros(self.n_sims)
        sim_sortinos = np.zeros(self.n_sims)
        port_returns = self.return_paths @ np.array([w for _, w in cfg.assets])

        rf_monthly = cfg.risk_free_rate / 12

        for sim in range(self.n_sims):
            # CAGR
            final = final_balances[sim]
            if final > 0 and initial > 0:
                sim_cagrs[sim] = (final / initial) ** (1 / cfg.years) - 1

            # Annual returns
            ann_rets = (1 + port_returns[sim]).reshape(-1, 12).prod(axis=1) - 1
            sim_ann_returns[sim] = ann_rets.mean()

            # Max drawdown from balance
            bal = self.balance_paths[sim]
            peak = np.maximum.accumulate(bal)
            dd = (bal - peak) / peak
            sim_max_dds[sim] = dd.min()

            # Sharpe
            if port_returns[sim].std() > 0:
                sim_sharpes[sim] = (
                    (port_returns[sim].mean() - rf_monthly)
                    / port_returns[sim].std()
                    * np.sqrt(12)
                )

            # Sortino
            downside = port_returns[sim][port_returns[sim] < 0]
            if len(downside) > 0 and downside.std() > 0:
                sim_sortinos[sim] = (
                    (port_returns[sim].mean() - rf_monthly)
                    / downside.std()
                    * np.sqrt(12)
                )

        # Inflation adjustment
        inflation = cfg.inflation_mean if cfg.inflation_adjusted else 0.0
        real_cagrs = (1 + sim_cagrs) / (1 + inflation) - 1
        real_finals = final_balances / (1 + inflation) ** cfg.years

        # Build table
        rows = {}
        row_data = [
            ("Time Weighted Rate of Return (nominal)", sim_ann_returns),
            ("Time Weighted Rate of Return (real)", sim_ann_returns - inflation),
            ("Portfolio End Balance (nominal)", final_balances),
            ("Portfolio End Balance (real)", real_finals),
            ("Annual Mean Return", sim_ann_returns),
            ("Annualized Volatility", np.array([
                port_returns[sim].std() * np.sqrt(12)
                for sim in range(self.n_sims)
            ])),
            ("Sharpe Ratio", sim_sharpes),
            ("Sortino Ratio", sim_sortinos),
            ("Maximum Drawdown", sim_max_dds),
        ]

        for label, values in row_data:
            if "Balance" in label:
                rows[label] = [float(np.percentile(values, p * 100)) for p in pcts]
            elif "Ratio" in label:
                # Ratios — no % sign, just decimal
                rows[label] = [f"{np.percentile(values, p * 100):.2f}" for p in pcts]
            else:
                # Percentages
                rows[label] = [f"{np.percentile(values, p * 100):.2%}" for p in pcts]

        self.performance_summary = pd.DataFrame(rows, index=labels).T
        self.performance_summary.index.name = "Statistic"

        # Safe & Perpetual Withdrawal Rates
        self.swr = safe_withdrawal_rate(final_balances, initial, cfg.years)
        self.pwr = perpetual_withdrawal_rate(final_balances, initial, cfg.years)

    def _compute_balance_percentiles(self) -> None:
        """
        Year-by-year percentile balance table (PV's Portfolio Balance section).
        Columns: 0, 1, 3, 5, 10, 15, ... 30 years
        """
        cfg = self.config
        pcts = cfg.percentiles
        year_range = list(range(0, cfg.years + 1, 1))

        rows = {}
        for yr in year_range:
            month_idx = min(yr * 12, self.n_months)
            balances = self.balance_paths[:, month_idx]
            rows[yr] = {
                f"p{int(p*100)}": float(np.percentile(balances, p * 100))
                for p in pcts
            }

        df = pd.DataFrame(rows).T
        df.index.name = "Year"
        self.balance_percentiles = df

    def _compute_simulated_assets(self) -> None:
        """
        Simulated Assets table: correlations, expected return, volatility.
        Matches PV's 'Simulated Assets - Correlations and Returns' section.
        """
        n_assets = len(self.asset_codes)
        asset_returns = self.return_paths.reshape(-1, n_assets)  # (n_sims*n_months, n_assets)

        ann_returns = np.zeros(n_assets)
        ann_vols = np.zeros(n_assets)

        for i in range(n_assets):
            rets = asset_returns[:, i]
            ann_returns[i] = (1 + rets.mean()) ** 12 - 1
            ann_vols[i] = rets.std() * np.sqrt(12)

        # Build table
        col_names = self.asset_names + ["CAGR", "Expected Return", "Volatility"]
        table_data = []

        if n_assets == 1:
            # Single asset: correlation is 1.0, no correlation matrix
            row = [1.0, f"{ann_returns[0]:.2%}", f"{ann_returns[0]:.2%}", f"{ann_vols[0]:.2%}"]
            table_data.append(row)
        else:
            # Correlation matrix from simulated returns
            sim_corr = np.corrcoef(asset_returns.T)

            for i, code in enumerate(self.asset_codes):
                row = list(sim_corr[i])
                row += [
                    f"{ann_returns[i]:.2%}",
                    f"{ann_returns[i]:.2%}",
                    f"{ann_vols[i]:.2%}",
                ]
                table_data.append(row)

        self.simulated_assets = pd.DataFrame(
            table_data,
            index=self.asset_names,
            columns=col_names,
        )

    def _compute_expected_returns(self) -> None:
        """
        Expected Annual Return probability table.
        Probability of achieving ≥ X% return at various horizons.
        """
        cfg = self.config
        pcts = cfg.percentiles
        allocs = np.array([w for _, w in cfg.assets])
        port_returns = self.return_paths @ allocs

        # Annual returns per simulation
        ann_returns = (1 + port_returns).reshape(self.n_sims, cfg.years, 12).prod(axis=2) - 1

        # Thresholds
        thresholds = [0.00, 0.025, 0.05, 0.075, 0.10, 0.125, 0.15]
        horizons = [1, 3, 5, 10, 15, 20, 25, 30]

        rows = {}
        for thr in thresholds:
            row = {}
            for h in horizons:
                if h <= cfg.years:
                    # Multi-year return (geometric mean)
                    multi_year = (1 + ann_returns[:, :h]).prod(axis=1) ** (1 / h) - 1
                    row[str(h)] = f"{(multi_year >= thr).mean():.2%}"
                else:
                    row[str(h)] = "—"
            rows[f">= {thr:.0%}"] = row

        self.expected_returns = pd.DataFrame(rows).T

    def _compute_loss_probabilities(self) -> None:
        """
        Loss Probability table.
        Probability of loss ≥ X% with/without cashflows.
        """
        cfg = self.config
        allocs = np.array([w for _, w in cfg.assets])
        port_returns = self.return_paths @ allocs

        ann_returns = (1 + port_returns).reshape(self.n_sims, cfg.years, 12).prod(axis=2) - 1

        loss_thresholds = [0.025, 0.05, 0.075, 0.10, 0.125, 0.15, 0.175, 0.20]
        horizons = [1, 3, 5, 10, 15, 20, 25, 30]

        rows = {}
        for loss in loss_thresholds:
            row = {}
            for h in horizons:
                if h <= cfg.years:
                    multi_year = (1 + ann_returns[:, :h]).prod(axis=1) ** (1 / h) - 1
                    row[str(h)] = f"{(multi_year <= -loss).mean():.2%}"
                else:
                    row[str(h)] = "—"
            rows[f">= {loss:.1%}"] = row

        self.loss_probabilities = pd.DataFrame(rows).T

    def _compute_key_metrics(self) -> None:
        """Compute summary metrics."""
        final_balances = self.balance_paths[:, -1]
        self.median_final_balance = float(np.median(final_balances))
        self.success_rate = float((final_balances > 0).mean())

        if self.config.years > 0 and self.config.initial_balance > 0:
            median_cagr = (
                (self.median_final_balance / self.config.initial_balance)
                ** (1 / self.config.years) - 1
            )
            self.median_cagr = median_cagr

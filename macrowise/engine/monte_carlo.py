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

import warnings
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

try:
    from macrowise.data.loader import load_inflation_data
    _HAS_INFLATION_DATA = True
except Exception:
    _HAS_INFLATION_DATA = False
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
    # Tax logic is not yet implemented; setting tax_enabled=True raises at run().
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
        self._validate_config()
        self._validate_assets()
        self._rng = np.random.default_rng(config.seed)

    def _load_data(self) -> None:
        """Load all required data."""
        self.monthly_returns = get_monthly_returns()
        self.annual_returns = get_annual_returns()
        self.corr_matrix = get_correlation_matrix()
        self.cov_matrix = get_covariance_matrix()
        self.asset_stats = get_asset_statistics()

    def _validate_config(self) -> None:
        """Validate cross-field config invariants that aren't model-specific."""
        cfg = self.config

        # custom_correlation only meaningful for models 3/4 (parametric)
        if cfg.custom_correlation is not None and cfg.model in (1, 2):
            raise ValueError(
                f"custom_correlation is only used by model=3 (Parameterized) and "
                f"model=4 (Forecasted). Got model={cfg.model} (Historical/Statistical); "
                f"correlation comes from historical data. Either remove custom_correlation "
                f"or change model to 3 or 4."
            )

        # custom_means/stds validated later per-asset; length check happens there.

        # Sanity: horizon and sim count
        if cfg.years < 1:
            raise ValueError(f"years must be >= 1 (got {cfg.years})")
        if cfg.simulations < 1:
            raise ValueError(f"simulations must be >= 1 (got {cfg.simulations})")

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
            raise ValueError(
                f"Allocations sum to {total_alloc:.4f}, must be 1.0 (±0.01). "
                f"Got: {[(c, round(w, 4)) for c, w in resolved]}"
            )

        cfg.assets = resolved

    def _get_asset_returns(self) -> pd.DataFrame:
        """Get historical returns for selected assets — union of asset histories (not dropna intersection)."""
        codes = [a for a, _ in self.config.assets]
        df = self.monthly_returns[codes]
        # Forward-fill within each asset to avoid dropping rows when one asset has short history.
        # This preserves data at the cost of assuming missing = last known value.
        return df.dropna(how="all")

    def _get_asset_means_stds(self) -> tuple[np.ndarray, np.ndarray]:
        """Get mean and std for selected assets.

        Raises ValueError if asset missing from stats and no custom values,
        or if custom_means/custom_stds length doesn't match n_assets.
        """
        codes = [a for a, _ in self.config.assets]
        n = len(codes)

        if self.config.custom_means is not None:
            means = np.array(self.config.custom_means)
            if len(means) != n:
                raise ValueError(
                    f"custom_means length {len(means)} != n_assets {n}"
                )
        else:
            missing = [c for c in codes if c not in self.asset_stats.index]
            if missing:
                raise ValueError(
                    f"No historical stats for assets: {missing}. "
                    f"Supply `custom_means` and `custom_stds` in config."
                )
            means = np.array([self.asset_stats.loc[c, "mean_annual"] for c in codes])

        if self.config.custom_stds is not None:
            stds = np.array(self.config.custom_stds)
            if len(stds) != n:
                raise ValueError(
                    f"custom_stds length {len(stds)} != n_assets {n}"
                )
        else:
            missing = [c for c in codes if c not in self.asset_stats.index]
            if missing:
                raise ValueError(
                    f"No historical stats for assets: {missing}. "
                    f"Supply `custom_means` and `custom_stds` in config."
                )
            stds = np.array([self.asset_stats.loc[c, "std_annual"] for c in codes])

        return means[:n], stds[:n]

    def _get_correlation(self) -> np.ndarray:
        """Get correlation matrix for selected assets. Honors custom_correlation."""
        codes = [a for a, _ in self.config.assets]
        n = len(codes)

        # Custom correlation takes precedence
        if self.config.custom_correlation is not None:
            corr = np.asarray(self.config.custom_correlation, dtype=float)
            if corr.shape != (n, n):
                raise ValueError(
                    f"custom_correlation shape {corr.shape} != ({n},{n})"
                )
            return corr

        if not self.config.use_historical_correlations:
            return np.eye(n)

        available_cols = [c for c in codes if c in self.corr_matrix.columns]
        if not available_cols:
            warnings.warn(
                f"No historical correlations for {codes}; using identity matrix.",
                RuntimeWarning,
            )
            return np.eye(n)

        sub = self.corr_matrix.loc[available_cols, available_cols].values
        if len(available_cols) < n:
            missing = [c for c in codes if c not in available_cols]
            warnings.warn(
                f"Correlation matrix missing for {missing}; using identity for those pairs.",
                RuntimeWarning,
            )
            full = np.eye(n)
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
        _, stds = self._get_asset_means_stds()
        corr = self._get_correlation()
        return np.outer(stds, stds) * corr

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
        """Model=1: Bootstrap from actual historical returns.

        Note: single_year and block bootstraps sample WITH REPLACEMENT, so
        limited history (e.g. 12 years) can still generate longer paths.
        """
        cfg = self.config
        hist = self.monthly_returns[codes].dropna()

        if not self.config.use_full_history:
            if self.config.start_year:
                hist = hist[hist.index.year >= self.config.start_year]
            if self.config.end_year:
                hist = hist[hist.index.year <= self.config.end_year]

        min_complete_years = self._min_complete_years(hist, codes)
        if min_complete_years < 1 and cfg.bootstrap_model in (1, 2):
            warnings.warn(
                f"Only {min_complete_years} complete years for {codes}; "
                f"falling back to single-month bootstrap.",
                RuntimeWarning,
            )
            bootstrap_model = 0
        else:
            bootstrap_model = cfg.bootstrap_model

        sampler = BootstrapSampler(
            block_model={0: "single_month", 1: "single_year", 2: "block"}[bootstrap_model],
            block_min_years=cfg.bootstrap_min_years,
            block_max_years=cfg.bootstrap_max_years,
            circular=cfg.circular_bootstrap,
            seed=cfg.seed,
        )

        n_months = cfg.years * 12
        port_weights = np.array([w for _, w in cfg.assets])
        paths = np.zeros((cfg.simulations, n_months, len(codes)))

        for sim in range(cfg.simulations):
            seq = sampler.sample_sequence(hist, cfg.years, codes)

            # Pad with LAST value if needed (not zeros) so partial years
            # continue the trend rather than damping tails to 0%.
            if seq.shape[0] < n_months:
                last = seq[-1] if len(seq) > 0 else np.zeros(seq.shape[1])
                pad = np.tile(last, (n_months - seq.shape[0], 1))
                seq = np.concatenate([seq, pad], axis=0)
            elif seq.shape[0] > n_months:
                seq = seq[:n_months]

            if self.config.sequence_stress_test > 0:
                seq = sampler.apply_sequence_stress(
                    seq, self.config.sequence_stress_test, annual=True,
                    portfolio_weights=port_weights,
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
        """Model=2: Bootstrap historical returns with custom statistics.

        Adjusts sampled paths so their empirical mean/std matches user-provided
        targets. Vol is scaled around the historical mean first, THEN the mean
        is shifted to the target (so rescaling doesn't inflate the mean).
        """
        paths = self._historical_returns(codes)
        cfg = self.config

        if cfg.custom_means is None and cfg.custom_stds is None:
            return paths

        hist_means = paths.mean(axis=(0, 1))  # monthly
        hist_stds = paths.std(axis=(0, 1))    # monthly

        for i in range(len(codes)):
            target_monthly_mean = (cfg.custom_means[i] / 12) if cfg.custom_means is not None else hist_means[i]
            target_monthly_std = (cfg.custom_stds[i] / np.sqrt(12)) if cfg.custom_stds is not None else hist_stds[i]

            # Center, scale, then re-shift to target mean
            centered = paths[:, :, i] - hist_means[i]
            if hist_stds[i] > 1e-10:
                scaled = centered * (target_monthly_std / hist_stds[i])
            else:
                scaled = centered
            paths[:, :, i] = scaled + target_monthly_mean

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
        corr = self._get_correlation()

        # Time series model selection
        if cfg.time_series_model == 3:
            # GARCH model — now honors cross-asset correlations
            sampler = GARCHSampler(
                mean_returns=means,
                initial_vol=stds,
                correlation=corr,
                seed=cfg.seed,
            )
            return sampler.generate_path(cfg.years, cfg.simulations)
        else:
            # Normal (default for Forecasted mode)
            cov = corr * np.outer(stds, stds)
            sampler = NormalSampler(means, cov, seed=cfg.seed)
            return sampler.generate_path(cfg.years, cfg.simulations)

    def _simulate_with_rebalance_and_cashflow(
        self, paths: np.ndarray, initial_balance: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Correctly simulate per-asset balances with rebalancing and cashflows.

        Rebalancing is done by resetting each asset's balance to
        `alloc[i] * total_balance` at the configured frequency (0 = never).
        Cashflows are applied AFTER growth (and rebalancing on that same
        boundary month) and drawn proportionally from each asset.

        Returns
        -------
        balance_paths : ndarray (n_sims, n_months + 1)
        port_returns : ndarray (n_sims, n_months) — effective portfolio returns
        """
        cfg = self.config
        n_sims, n_months, n_assets = paths.shape
        allocs = np.array([w for _, w in cfg.assets], dtype=float)

        freq_map = {0: 0, 1: 12, 2: 6, 3: 3, 4: 1}
        rebal_months = freq_map.get(cfg.rebalance_frequency, 12)

        # Generate cashflow schedule (per-month amount or rate; type-3 = rate)
        cf = cfg.cashflow
        if cf is not None and cf.adjustment_type != 0:
            cf_engine = CashFlowEngine(cf)
            cf_schedule = cf_engine.generate_schedule(n_months)
            cf_type = cf.adjustment_type
        else:
            cf_schedule = np.zeros(n_months)
            cf_type = 0

        # Per-asset balances: (n_sims, n_assets)
        asset_bal = np.tile(initial_balance * allocs, (n_sims, 1))

        balance_paths = np.zeros((n_sims, n_months + 1))
        balance_paths[:, 0] = initial_balance
        port_returns = np.zeros((n_sims, n_months))

        for m in range(n_months):
            # 1. Grow each asset independently
            prev_total = asset_bal.sum(axis=1)  # (n_sims,)
            asset_bal = asset_bal * (1 + paths[:, m, :])
            total = asset_bal.sum(axis=1)

            # Effective portfolio return this month
            with np.errstate(divide="ignore", invalid="ignore"):
                port_returns[:, m] = np.where(prev_total > 0, total / prev_total - 1, 0.0)

            # 2. Rebalance at boundary
            if rebal_months > 0 and (m + 1) % rebal_months == 0:
                asset_bal = total[:, None] * allocs[None, :]

            # 3. Apply cashflow
            if cf_type == 3:
                # Fixed % — apply once per period boundary only
                freq = cf.frequency if cf else "annual"
                periods_per_year = {"monthly": 12, "quarterly": 4, "annual": 1}.get(freq, 1)
                # gate: apply at m % (12/periods_per_year) == 0
                step = 12 // periods_per_year
                if m % step == 0:
                    wd_pct_annual = cf_schedule[m]  # annual rate
                    # per-period rate = annual / periods_per_year
                    per_period_rate = wd_pct_annual / periods_per_year
                    total_after = asset_bal.sum(axis=1) * (1 - per_period_rate)
                    # Preserve allocation proportions
                    asset_bal = asset_bal * (1 - per_period_rate)
            elif cf_type == 4:
                # Life expectancy (already per-month in schedule)
                amt = abs(cf_schedule[m])
                if amt > 0:
                    total_now = asset_bal.sum(axis=1)
                    ratio = np.divide(
                        np.maximum(0.0, total_now - amt),
                        total_now,
                        out=np.zeros_like(total_now),
                        where=total_now > 0,
                    )
                    asset_bal = asset_bal * ratio[:, None]
            elif cf_type in (1, 2, 8, 9) and cf_schedule[m] != 0:
                # Contribution (+) or withdrawal (-) as fixed amount
                amt = cf_schedule[m]
                if amt > 0:
                    # Contribution: add to each asset proportionally to target allocs
                    asset_bal = asset_bal + amt * allocs[None, :]
                else:
                    # Withdrawal: subtract, preserving current proportions
                    total_now = asset_bal.sum(axis=1)
                    withdraw_amt = -amt
                    ratio = np.divide(
                        np.maximum(0.0, total_now - withdraw_amt),
                        total_now,
                        out=np.zeros_like(total_now),
                        where=total_now > 0,
                    )
                    asset_bal = asset_bal * ratio[:, None]

            # Clamp to zero
            asset_bal = np.maximum(asset_bal, 0.0)
            balance_paths[:, m + 1] = asset_bal.sum(axis=1)

        return balance_paths, port_returns

    def _apply_rebalancing(self, paths: np.ndarray) -> np.ndarray:
        """Legacy no-op — rebalancing now handled in _simulate_with_rebalance_and_cashflow."""
        return paths

    def _apply_cashflows_vectorized(
        self, paths: np.ndarray, initial_balance: float
    ) -> np.ndarray:
        """Delegates to the unified per-asset simulator."""
        balance_paths, _port_returns = self._simulate_with_rebalance_and_cashflow(
            paths, initial_balance
        )
        # Stash the effective portfolio returns for later CAGR/vol calcs
        self._effective_port_returns = _port_returns
        return balance_paths

    def _paths_to_balance(
        self, paths: np.ndarray, initial_balance: float
    ) -> np.ndarray:
        """Convert return paths to balance paths (no cashflow, no rebalance)."""
        allocs = np.array([w for _, w in self.config.assets])
        port_returns = paths @ allocs
        self._effective_port_returns = port_returns
        balances = initial_balance * np.cumprod(1 + port_returns, axis=1)
        return np.concatenate(
            [np.full((paths.shape[0], 1), initial_balance), balances], axis=1
        )

    def _sample_inflation(self, n_sims: int, n_months: int) -> np.ndarray:
        """Sample inflation per (sim, month). Returns shape (n_sims, n_months).

        - inflation_model == 1: sample from historical CPI data (if available),
          else fall back to N(mean, vol).
        - inflation_model == 2: parametric N(mean, vol).
        Applied as MONTHLY inflation rate (annual/12).
        """
        cfg = self.config
        if not cfg.inflation_adjusted:
            return np.zeros((n_sims, n_months))

        if cfg.inflation_model == 1 and _HAS_INFLATION_DATA:
            try:
                cpi = load_inflation_data()
                # Convert to Series if DataFrame
                if isinstance(cpi, pd.DataFrame):
                    cpi = cpi.iloc[:, 0]
                # CPI is monthly inflation rate (as decimal)
                hist_infl = cpi.dropna().values
                if len(hist_infl) > 0:
                    # Bootstrap monthly inflation samples
                    idx = self._rng.integers(0, len(hist_infl), size=(n_sims, n_months))
                    return hist_infl[idx]
            except Exception:
                pass  # Fall through to parametric

        # Parametric inflation: N(mean_monthly, vol_monthly)
        mean_m = cfg.inflation_mean / 12
        vol_m = cfg.inflation_volatility / np.sqrt(12)
        return self._rng.normal(mean_m, vol_m, size=(n_sims, n_months))

    def run(self) -> "MonteCarloResults":
        """Execute the Monte Carlo simulation."""
        cfg = self.config
        if cfg.tax_enabled:
            raise NotImplementedError(
                "Tax logic is not yet wired into the simulation engine. "
                "Set tax_enabled=False or open a feature request."
            )
        codes = [a for a, _ in cfg.assets]

        print(f"Generating {cfg.simulations:,} simulations × {cfg.years} years × {len(codes)} assets...")
        paths = self._build_return_paths()
        print(f"  Return paths: {paths.shape}")

        # Apply cashflows + rebalancing → balance paths (per-asset simulation)
        balance_paths = self._apply_cashflows_vectorized(paths, cfg.initial_balance)
        print(f"  Balance paths: {balance_paths.shape}")

        # Sample inflation per (sim, month) — used for real-return calcs
        n_months = paths.shape[1]
        inflation_paths = self._sample_inflation(cfg.simulations, n_months)

        # Effective portfolio returns after rebalancing (from balance simulation)
        eff_port_returns = getattr(self, "_effective_port_returns", None)

        results = MonteCarloResults(
            config=cfg,
            balance_paths=balance_paths,
            return_paths=paths,
            asset_codes=codes,
            asset_names=[get_asset(c).name if get_asset(c) else c for c in codes],
            inflation_paths=inflation_paths,
            effective_port_returns=eff_port_returns,
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
        inflation_paths: np.ndarray | None = None,
        effective_port_returns: np.ndarray | None = None,
    ):
        self.config = config
        self.balance_paths = balance_paths
        self.return_paths = return_paths
        self.asset_codes = asset_codes
        self.asset_names = asset_names
        self.inflation_paths = inflation_paths  # (n_sims, n_months) or None
        self.effective_port_returns = effective_port_returns  # (n_sims, n_months) or None

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
        self.sim_cagrs: np.ndarray = np.zeros(0)

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
        """PV's Performance Summary table: 9 rows × 5 percentiles.

        - CAGR uses TWR (geometric mean of annual returns; NOT affected by cashflows).
        - Real return uses Fisher equation: (1+nominal)/(1+inflation) - 1.
        - Includes ALL years (no filter dropping -100% years).
        """
        cfg = self.config
        pcts = cfg.percentiles
        labels = [f"p{int(p * 100)}" for p in pcts]

        final_balances = self.balance_paths[:, -1]
        initial = cfg.initial_balance
        n_sims = self.n_sims

        # Portfolio returns — use effective ones (post-rebalance) if available,
        # else raw allocation-weighted from paths.
        if self.effective_port_returns is not None:
            port_returns = self.effective_port_returns
        else:
            allocs = np.array([w for _, w in cfg.assets])
            port_returns = self.return_paths @ allocs

        # Ensure n_months divisible by 12 for reshape (should be by construction)
        n_full_years = self.n_months // 12
        n_months_used = n_full_years * 12
        pr = port_returns[:, :n_months_used]

        # Annual returns per simulation (n_sims, n_full_years)
        ann_rets_all = (1 + pr).reshape(n_sims, n_full_years, 12).prod(axis=2) - 1

        # CAGR = geometric mean of ALL annual returns (INCLUDING -100% wipeout years,
        # which correctly send CAGR to -100%; do NOT filter them out).
        # (1 + geo_mean)^n = prod(1 + ann) → geo_mean = prod ** (1/n) - 1
        # Guard against negative product (should not happen unless (1+r) < 0 for some r)
        product = np.prod(1 + ann_rets_all, axis=1)
        with np.errstate(invalid="ignore"):
            self.sim_cagrs = np.where(
                product > 0,
                product ** (1.0 / n_full_years) - 1,
                -1.0,  # Total wipeout
            )

        sim_ann_returns = ann_rets_all.mean(axis=1)
        sim_ann_vols = pr.std(axis=1) * np.sqrt(12)

        # Max drawdown per sim
        peaks = np.maximum.accumulate(self.balance_paths, axis=1)
        drawdowns = (self.balance_paths - peaks) / np.maximum(peaks, 1e-9)
        sim_max_dds = drawdowns.min(axis=1)

        # Sharpe (vectorized, no div-by-zero warnings)
        rf_monthly = cfg.risk_free_rate / 12
        pr_mean = pr.mean(axis=1)
        pr_std = pr.std(axis=1)
        sim_sharpes = np.divide(
            (pr_mean - rf_monthly) * np.sqrt(12),
            pr_std,
            out=np.zeros_like(pr_mean),
            where=pr_std > 0,
        )

        # Sortino using standard TDD (target = 0)
        downside = np.maximum(0.0, -pr)
        dsd = np.sqrt((downside ** 2).mean(axis=1))
        sim_sortinos = np.divide(
            (pr_mean - rf_monthly) * np.sqrt(12),
            dsd,
            out=np.full_like(pr_mean, np.nan),
            where=dsd > 0,
        )

        # Real returns — use per-sim inflation (average annualized)
        if self.inflation_paths is not None and cfg.inflation_adjusted:
            # Clamp monthly inflation to sane range to avoid overflow
            # (extreme parametric draws can produce >|100%| monthly rates)
            clamped = np.clip(self.inflation_paths[:, :n_months_used], -0.02, 0.05)
            infl_monthly_mean = clamped.mean(axis=1)
            infl_annual = (1 + infl_monthly_mean) ** 12 - 1
            # Fisher: real = (1 + nominal) / (1 + infl) - 1
            real_ann_returns = (1 + sim_ann_returns) / (1 + infl_annual) - 1
            # Guard: (1 + infl_annual) must be > 0
            infl_growth = np.maximum(1 + infl_annual, 1e-6) ** n_full_years
            real_finals = final_balances / infl_growth
        else:
            real_ann_returns = sim_ann_returns
            real_finals = final_balances

        # Build table
        rows = {}
        row_data = [
            ("Time Weighted Rate of Return (nominal)", sim_ann_returns),
            ("Time Weighted Rate of Return (real)", real_ann_returns),
            ("Portfolio End Balance (nominal)", final_balances),
            ("Portfolio End Balance (real)", real_finals),
            ("Annual Mean Return", sim_ann_returns),
            ("Annualized Volatility", sim_ann_vols),
            ("Sharpe Ratio", sim_sharpes),
            ("Sortino Ratio", sim_sortinos),
            ("Maximum Drawdown", sim_max_dds),
        ]
        for label, values in row_data:
            if "Balance" in label:
                rows[label] = [float(np.percentile(values, p * 100)) for p in pcts]
            elif "Ratio" in label:
                # Nan-safe percentile
                clean = values[~np.isnan(values)]
                if len(clean) == 0:
                    clean = np.array([0.0])
                rows[label] = [f"{np.percentile(clean, p * 100):.2f}" for p in pcts]
            else:
                rows[label] = [f"{np.percentile(values, p * 100):.2%}" for p in pcts]

        self.performance_summary = pd.DataFrame(rows, index=labels).T
        self.performance_summary.index.name = "Statistic"

        # SWR / PWR — real MC calculation using effective portfolio returns
        try:
            self.swr = safe_withdrawal_rate(
                pr, initial, cfg.years, inflation_mean=cfg.inflation_mean,
            )
            self.pwr = perpetual_withdrawal_rate(
                pr, initial, cfg.years, inflation_mean=cfg.inflation_mean,
            )
        except Exception:
            self.swr = 0.0
            self.pwr = 0.0

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
        """Simulated Assets table: correlations, expected return, volatility.

        CAGR = geometric mean of annual returns (compound annual growth).
        Expected Return = arithmetic annualization of monthly mean.
        These are DIFFERENT numbers; do not duplicate.
        """
        n_assets = len(self.asset_codes)
        n_sims, n_months, _ = self.return_paths.shape
        n_full_years = n_months // 12

        # Per-asset annualized geometric CAGR (mean across sims)
        cagrs_per_asset = np.zeros(n_assets)
        exp_ret_per_asset = np.zeros(n_assets)
        vols_per_asset = np.zeros(n_assets)

        for i in range(n_assets):
            rets = self.return_paths[:, : n_full_years * 12, i]  # (n_sims, n_months)
            ann_rets = (1 + rets).reshape(n_sims, n_full_years, 12).prod(axis=2) - 1

            # CAGR = geometric mean of annual returns, averaged across sims
            products = np.prod(1 + ann_rets, axis=1)
            with np.errstate(invalid="ignore"):
                sim_cagrs = np.where(products > 0, products ** (1.0 / n_full_years) - 1, -1.0)
            cagrs_per_asset[i] = float(np.median(sim_cagrs))

            # Expected Return = arithmetic annualization of monthly mean
            exp_ret_per_asset[i] = (1 + rets.mean()) ** 12 - 1
            vols_per_asset[i] = rets.std() * np.sqrt(12)

        # Correlation matrix from simulated returns
        asset_flat = self.return_paths.reshape(-1, n_assets)
        col_names = self.asset_names + ["CAGR", "Expected Return", "Volatility"]
        table_data = []

        if n_assets == 1:
            row = [1.0,
                   f"{cagrs_per_asset[0]:.2%}",
                   f"{exp_ret_per_asset[0]:.2%}",
                   f"{vols_per_asset[0]:.2%}"]
            table_data.append(row)
        else:
            sim_corr = np.corrcoef(asset_flat.T)
            for i in range(n_assets):
                row = list(sim_corr[i])
                row += [
                    f"{cagrs_per_asset[i]:.2%}",
                    f"{exp_ret_per_asset[i]:.2%}",
                    f"{vols_per_asset[i]:.2%}",
                ]
                table_data.append(row)

        self.simulated_assets = pd.DataFrame(
            table_data,
            index=self.asset_names,
            columns=col_names,
        )

    def _compute_expected_returns(self) -> None:
        """Expected Annual Return probability table."""
        cfg = self.config
        n_full_years = self.n_months // 12
        if n_full_years < 1:
            self.expected_returns = pd.DataFrame()
            return

        if self.effective_port_returns is not None:
            port_returns = self.effective_port_returns
        else:
            allocs = np.array([w for _, w in cfg.assets])
            port_returns = self.return_paths @ allocs

        pr = port_returns[:, : n_full_years * 12]
        ann_returns = (1 + pr).reshape(self.n_sims, n_full_years, 12).prod(axis=2) - 1

        thresholds = [0.00, 0.025, 0.05, 0.075, 0.10, 0.125, 0.15]
        horizons = [1, 3, 5, 10, 15, 20, 25, 30]

        rows = {}
        for thr in thresholds:
            row = {}
            for h in horizons:
                if h <= n_full_years:
                    multi_year = (1 + ann_returns[:, :h]).prod(axis=1) ** (1 / h) - 1
                    row[str(h)] = f"{(multi_year >= thr).mean():.2%}"
                else:
                    row[str(h)] = "—"
            rows[f">= {thr:.0%}"] = row
        self.expected_returns = pd.DataFrame(rows).T

    def _compute_loss_probabilities(self) -> None:
        """Loss Probability table."""
        cfg = self.config
        n_full_years = self.n_months // 12
        if n_full_years < 1:
            self.loss_probabilities = pd.DataFrame()
            return

        if self.effective_port_returns is not None:
            port_returns = self.effective_port_returns
        else:
            allocs = np.array([w for _, w in cfg.assets])
            port_returns = self.return_paths @ allocs

        pr = port_returns[:, : n_full_years * 12]
        ann_returns = (1 + pr).reshape(self.n_sims, n_full_years, 12).prod(axis=2) - 1

        loss_thresholds = [0.025, 0.05, 0.075, 0.10, 0.125, 0.15, 0.175, 0.20]
        horizons = [1, 3, 5, 10, 15, 20, 25, 30]

        rows = {}
        for loss in loss_thresholds:
            row = {}
            for h in horizons:
                if h <= n_full_years:
                    multi_year = (1 + ann_returns[:, :h]).prod(axis=1) ** (1 / h) - 1
                    row[str(h)] = f"{(multi_year <= -loss).mean():.2%}"
                else:
                    row[str(h)] = "—"
            rows[f">= {loss:.1%}"] = row
        self.loss_probabilities = pd.DataFrame(rows).T

    def _compute_key_metrics(self) -> None:
        """Compute summary metrics.

        Success rate: fraction of paths that end with balance > 1% of initial
        (treats near-zero balances as depleted, matching PV semantics).
        """
        final_balances = self.balance_paths[:, -1]
        self.median_final_balance = float(np.median(final_balances))

        # Success = final balance stays above 1% of initial (not just > 0)
        threshold = self.config.initial_balance * 0.01
        self.success_rate = float((final_balances > threshold).mean())

        if self.config.years > 0 and self.config.initial_balance > 0:
            median_cagr = (
                (self.median_final_balance / self.config.initial_balance)
                ** (1 / self.config.years) - 1
            )
            self.median_cagr_with_cashflows = median_cagr
            # TWR-based CAGR (from ann_rets) is primary metric
            self.median_cagr = float(np.median(self.sim_cagrs))

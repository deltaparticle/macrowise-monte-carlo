"""
Bootstrap Sampler — Historical Returns mode (PV model=1).

Implements PV's 3 bootstrap types:
  1. Single Month  — resample individual months
  2. Single Year   — resample entire years (preserves seasonality)
  3. Block of Years — resample variable-length blocks

Also supports:
  - Circular bootstrapping (wrap-around)
  - Sequence stress test (worst N years first)
"""

import numpy as np
import pandas as pd
from typing import Optional


class BootstrapSampler:
    """
    Historical bootstrap sampler matching PV's implementation.

    Parameters
    ----------
    block_model : str
        'single_month', 'single_year', or 'block'
    block_min_years : int
        Minimum block length (for block mode)
    block_max_years : int
        Maximum block length (for block mode)
    circular : bool
        Allow circular wrapping at end of history
    seed : int | None
        Random seed for reproducibility
    """

    def __init__(
        self,
        block_model: str = "single_year",
        block_min_years: int = 1,
        block_max_years: int = 20,
        circular: bool = True,
        seed: int | None = None,
    ):
        self.block_model = block_model
        self.block_min_years = block_min_years
        self.block_max_years = block_max_years
        self.circular = circular
        self._rng = np.random.default_rng(seed)

    def set_seed(self, seed: int | None) -> None:
        self._rng = np.random.default_rng(seed)

    def sample_sequence(
        self,
        historical_returns: pd.DataFrame,
        n_years: int,
        assets: list[str] | None = None,
    ) -> np.ndarray:
        """
        Generate a simulated return sequence by bootstrapping from history.

        Parameters
        ----------
        historical_returns : DataFrame
            Monthly returns indexed by date, columns = assets
        n_years : int
            Number of years to simulate
        assets : list[str] | None
            Which assets to include. If None, use all.

        Returns
        -------
        ndarray of shape (n_months, n_assets)
        """
        if assets is None:
            assets = list(historical_returns.columns)

        hist = historical_returns[assets].dropna()
        n_months = n_years * 12

        if len(hist) == 0:
            raise ValueError("No historical data available for selected assets.")

        if self.block_model == "single_month":
            return self._sample_single_month(hist, n_months)
        elif self.block_model == "single_year":
            return self._sample_single_year(hist, n_years)
        elif self.block_model == "block":
            return self._sample_block(hist, n_years)
        else:
            raise ValueError(f"Unknown block_model: {self.block_model}")

    def _sample_single_month(
        self, hist: pd.DataFrame, n_months: int
    ) -> np.ndarray:
        """Resample individual months."""
        n_assets = hist.shape[1]
        indices = self._rng.integers(0, len(hist), size=n_months)
        return hist.values[indices]

    def _sample_single_year(
        self, hist: pd.DataFrame, n_years: int
    ) -> np.ndarray:
        """
        Resample entire years. Preserves within-year correlation.

        Only complete years (exactly 12 months) are used.
        The returned sequence has n_years * 12 rows.
        """
        # Find complete calendar years only
        hist_yearly = {}
        for year, group in hist.groupby(hist.index.year):
            if len(group) == 12:
                hist_yearly[year] = group.values  # shape (12, n_assets)

        if not hist_yearly:
            raise ValueError(
                f"No complete (12-month) years found. "
                f"Available years have months: "
                f"{sorted(hist.groupby(hist.index.year).size().to_dict().items())}"
            )

        years = list(hist_yearly.keys())
        results = []

        for _ in range(n_years):
            year_key = self._rng.choice(years)
            results.append(hist_yearly[year_key])

        return np.concatenate(results, axis=0)  # shape (n_years*12, n_assets)

    def _sample_block(
        self, hist: pd.DataFrame, n_years: int
    ) -> np.ndarray:
        """Sample variable-length blocks of years.

        Supports circular bootstrapping when self.circular=True (wraps around
        end of history).
        """
        blocks = []
        years_generated = 0
        hist_len = len(hist)
        hist_vals = hist.values

        while years_generated < n_years:
            block_len = int(self._rng.integers(
                self.block_min_years,
                self.block_max_years + 1
            ))
            if years_generated + block_len > n_years:
                block_len = n_years - years_generated

            block_months = block_len * 12

            if self.circular:
                # Circular: any start position [0, hist_len), wrap if needed
                start = int(self._rng.integers(0, hist_len))
                if start + block_months <= hist_len:
                    block = hist_vals[start:start + block_months]
                else:
                    # Wrap around
                    tail = hist_vals[start:]
                    remaining = block_months - len(tail)
                    head = hist_vals[:remaining]
                    block = np.concatenate([tail, head], axis=0)
            else:
                # Non-circular: start ∈ [0, hist_len - block_months]
                max_start = hist_len - block_months
                if max_start < 0:
                    # Block bigger than history: use all available
                    block = hist_vals
                else:
                    # Inclusive upper bound: max_start + 1
                    start = int(self._rng.integers(0, max_start + 1))
                    block = hist_vals[start:start + block_months]

            blocks.append(block)
            years_generated += block_len

        return np.concatenate(blocks, axis=0)

    def apply_sequence_stress(
        self,
        returns_sequence: np.ndarray,
        n_worst_first: int,
        annual: bool = True,
        portfolio_weights: np.ndarray | None = None,
    ) -> np.ndarray:
        """Apply sequence stress: put worst N years first.

        Parameters
        ----------
        returns_sequence : ndarray, shape (n_months, n_assets)
        n_worst_first : int
            Number of worst years to place first.
        annual : bool
            If True, rank by portfolio-weighted annual returns.
            If False, rank by portfolio-weighted total-period return
            (which for monthly-level stress reduces to a compound sort).
        portfolio_weights : ndarray, shape (n_assets,), optional
            Portfolio weights for ranking. If None, uses equal weights.
        """
        if n_worst_first <= 0:
            return returns_sequence

        n_assets = returns_sequence.shape[1]
        if portfolio_weights is None:
            portfolio_weights = np.ones(n_assets) / n_assets
        portfolio_weights = np.asarray(portfolio_weights).flatten()

        n_years = returns_sequence.shape[0] // 12
        if n_years < 2:
            return returns_sequence
        reshaped = returns_sequence[: n_years * 12].reshape(n_years, 12, n_assets)

        if annual:
            annual_asset_returns = (1 + reshaped).prod(axis=1) - 1  # (n_years, n_assets)
            # PORTFOLIO-weighted annual return (not equal-weight)
            port_annual = annual_asset_returns @ portfolio_weights
        else:
            # Compound monthly portfolio returns per year, then annualize
            monthly_port = reshaped @ portfolio_weights  # (n_years, 12)
            port_annual = (1 + monthly_port).prod(axis=1) - 1

        sorted_idx = np.argsort(port_annual)
        worst_indices = sorted_idx[:n_worst_first]
        rest_indices = sorted_idx[n_worst_first:]
        # After stress block, restore rest to CHRONOLOGICAL order (not sorted)
        rest_chronological = np.sort(rest_indices)
        reordered = np.concatenate(
            [reshaped[worst_indices], reshaped[rest_chronological]], axis=0
        )
        return reordered.reshape(-1, n_assets)


class YearlyBootstrap:
    """
    Simplified yearly bootstrap — resample complete calendar years.
    This preserves within-year autocorrelation and seasonality.
    """

    def __init__(self, seed: int | None = None):
        self._rng = np.random.default_rng(seed)

    def sample(
        self, monthly_returns: pd.DataFrame, n_years: int, assets: list[str]
    ) -> np.ndarray:
        """
        Return ndarray of shape (n_years * 12, n_assets).

        Shuffles complete years from the historical record.
        """
        hist = monthly_returns[assets].dropna()
        years_available = sorted(hist.index.year.unique())
        yearly_data: dict[int, np.ndarray] = {}

        for yr in years_available:
            yr_data = hist[hist.index.year == yr].values
            if len(yr_data) == 12:  # Only complete years
                yearly_data[yr] = yr_data

        available = list(yearly_data.values())
        if not available:
            raise ValueError("No complete years of data.")

        sampled = []
        for _ in range(n_years):
            idx = self._rng.integers(0, len(available))
            sampled.append(available[idx])

        return np.concatenate(sampled, axis=0)

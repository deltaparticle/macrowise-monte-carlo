"""
Parametric Sampler — Forecasted, Statistical, and Parameterized modes.

Implements PV's three non-historical simulation models:
  - Forecasted Returns (model=4): user-specified mean/std + correlations
  - Statistical Returns (model=2): bootstrap returns + custom stats
  - Parameterized Returns (model=3): N(μ,σ) or t-distribution draws

Also supports:
  - Fat-tailed distributions (Student's t with configurable dof)
  - GARCH model (Normal/GARCH time series)
"""

import numpy as np
import pandas as pd
from typing import Optional
from scipy import stats


class NormalSampler:
    """Multivariate normal return generator with correlation."""

    def __init__(
        self,
        mean_returns: np.ndarray,
        covariance: np.ndarray,
        seed: int | None = None,
    ):
        """
        Parameters
        ----------
        mean_returns : ndarray, shape (n_assets,)
            Annual mean returns (decimal).
        covariance : ndarray, shape (n_assets, n_assets)
            Annual covariance matrix.
        """
        self.mean = mean_returns.astype(float)
        self.cov = covariance.astype(float)
        self.n_assets = len(mean_returns)
        self._rng = np.random.default_rng(seed)

    def set_seed(self, seed: int | None) -> None:
        self._rng = np.random.default_rng(seed)

    def annual_returns(self, n_sims: int) -> np.ndarray:
        """Draw n_sims annual returns. Shape: (n_sims, n_assets)."""
        return self._rng.multivariate_normal(self.mean, self.cov, size=n_sims)

    def monthly_returns(self, n_sims: int) -> np.ndarray:
        """Draw monthly returns assuming annual → monthly scaling."""
        monthly_mean = self.mean / 12
        monthly_cov = self.cov / 12
        draws = self._rng.multivariate_normal(
            monthly_mean, monthly_cov, size=n_sims * 12
        )
        return draws.reshape(n_sims, 12, self.n_assets)

    def generate_path(
        self, n_years: int, n_sims: int
    ) -> np.ndarray:
        """
        Generate full return paths.

        Returns
        -------
        ndarray of shape (n_sims, n_years * 12, n_assets)
        """
        all_returns = []
        for _ in range(n_years):
            annual = self.annual_returns(n_sims)  # (n_sims, n_assets)
            monthly = annual[:, np.newaxis, :] / 12  # (n_sims, 1, n_assets)
            # Spread across 12 months with some noise
            monthly_noise = self._rng.normal(
                0, np.sqrt(np.diag(self.cov) / 12),
                size=(n_sims, 12, self.n_assets)
            )
            month_returns = monthly + monthly_noise
            all_returns.append(month_returns)

        return np.concatenate(all_returns, axis=1)


class FatTailedSampler:
    """
    Fat-tailed (Student's t-distribution) return generator.

    PV's Parameterized mode supports fat-tailed returns to better
    capture extreme market events that a Normal distribution misses.
    """

    def __init__(
        self,
        mean_returns: np.ndarray,
        std_returns: np.ndarray,
        dof: int = 30,
        correlation: np.ndarray | None = None,
        seed: int | None = None,
    ):
        """
        Parameters
        ----------
        mean_returns : ndarray, shape (n_assets,)
        std_returns : ndarray, shape (n_assets,)
        dof : int
            Degrees of freedom. Lower = fatter tails.
            PV default is 30 (close to Normal, PV range 5-50).
        correlation : ndarray, shape (n_assets, n_assets)
            Correlation matrix.
        """
        self.mean = np.asarray(mean_returns, dtype=float)
        self.std = np.asarray(std_returns, dtype=float)
        if dof <= 2:
            raise ValueError(f"FatTailedSampler requires dof > 2 (got {dof}); variance is undefined.")
        self.dof = dof
        self.correlation = correlation
        self.n_assets = len(mean_returns)
        self._rng = np.random.default_rng(seed)

    def set_seed(self, seed: int | None) -> None:
        self._rng = np.random.default_rng(seed)

    def generate_path(
        self, n_years: int, n_sims: int
    ) -> np.ndarray:
        """
        Generate correlated fat-tailed return paths.

        Uses a copula approach: draw from multivariate t, scale by mean/std.
        """
        n_months = n_years * 12
        monthly_mean = self.mean / 12
        monthly_std = self.std / np.sqrt(12)

        if self.correlation is not None:
            # Cholesky decomposition for correlation
            L = np.linalg.cholesky(self.correlation)
        else:
            L = np.eye(self.n_assets)

        # Draw from t-distribution
        t_draws = self._rng.standard_t(df=self.dof, size=(n_sims, n_months, self.n_assets))
        # Standardize to have unit variance
        t_draws = t_draws / np.sqrt(self.dof / (self.dof - 2))
        # Apply correlation
        correlated = t_draws @ L.T
        # Scale by mean and std
        returns = correlated * monthly_std[np.newaxis, np.newaxis, :] + monthly_mean[np.newaxis, np.newaxis, :]

        return returns


class GARCHSampler:
    """
    GARCH(1,1) return sampler for time-series mode.

    Captures volatility clustering — periods of high volatility
    tend to be followed by high volatility, and vice versa.
    """

    def __init__(
        self,
        mean_returns: np.ndarray,
        initial_vol: np.ndarray,
        omega: float = 1e-6,
        alpha: float = 0.08,
        beta: float = 0.90,
        seed: int | None = None,
    ):
        """
        Parameters
        ----------
        mean_returns : ndarray
            Annual mean returns.
        initial_vol : ndarray
            Initial annualized volatilities.
        omega : float
            GARCH constant term (long-run variance floor).
        alpha : float
            ARCH parameter (sensitivity to recent shocks).
        beta : float
            GARCH parameter (persistence).
        """
        self.mean = np.asarray(mean_returns, dtype=float)
        self.initial_vol = np.asarray(initial_vol, dtype=float)
        self.omega = omega
        self.alpha = alpha
        self.beta = beta
        self.n_assets = len(mean_returns)
        self._rng = np.random.default_rng(seed)

    def set_seed(self, seed: int | None) -> None:
        self._rng = np.random.default_rng(seed)

    def generate_path(
        self, n_years: int, n_sims: int
    ) -> np.ndarray:
        """Generate GARCH-filtered return paths."""
        n_months = n_years * 12
        monthly_mean = self.mean / 12
        monthly_vol = self.initial_vol / np.sqrt(12)

        returns = np.zeros((n_sims, n_months, self.n_assets))
        sigma2 = np.zeros((n_sims, n_months, self.n_assets))

        # Initialize variance
        sigma2[:, 0, :] = monthly_vol ** 2

        for t in range(n_months):
            if t > 0:
                # GARCH(1,1): sigma^2 = omega + alpha * r^2_{t-1} + beta * sigma^2_{t-1}
                prev_ret = returns[:, t - 1, :] ** 2
                sigma2[:, t, :] = (
                    self.omega
                    + self.alpha * prev_ret
                    + self.beta * sigma2[:, t - 1, :]
                )

            # Draw returns from normal with current volatility
            sigma = np.sqrt(np.maximum(sigma2[:, t, :], 1e-10))
            returns[:, t, :] = (
                self._rng.standard_normal((n_sims, self.n_assets)) * sigma
                + monthly_mean
            )

        return returns

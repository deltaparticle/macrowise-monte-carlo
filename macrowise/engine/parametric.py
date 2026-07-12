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
        """Generate correlated monthly return paths.

        Draws directly from multivariate N(monthly_mean, monthly_cov) — one
        independent draw per (sim, month). Correctly preserves the target
        annual variance when 12 months are compounded, without the double-
        counting variance inflation that arises when annual is drawn first
        and then noise is added per month.

        Returns
        -------
        ndarray, shape (n_sims, n_years * 12, n_assets)
        """
        n_months = n_years * 12
        monthly_mean = self.mean / 12
        monthly_cov = self.cov / 12
        draws = self._rng.multivariate_normal(
            monthly_mean, monthly_cov, size=(n_sims, n_months)
        )
        return draws  # (n_sims, n_months, n_assets)


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
    """GARCH(1,1) return sampler with cross-asset correlation.

    Captures volatility clustering. Correlations across assets are applied
    per-month via Cholesky decomposition of the correlation matrix.

    Long-run monthly variance floor = omega / (1 - alpha - beta). Set
    omega automatically from initial_vol if user passes omega=None.
    """

    def __init__(
        self,
        mean_returns: np.ndarray,
        initial_vol: np.ndarray,
        omega: float | None = None,
        alpha: float = 0.08,
        beta: float = 0.90,
        correlation: np.ndarray | None = None,
        seed: int | None = None,
    ):
        self.mean = np.asarray(mean_returns, dtype=float)
        self.initial_vol = np.asarray(initial_vol, dtype=float)
        if not (0 <= alpha < 1 and 0 <= beta < 1 and alpha + beta < 1):
            raise ValueError(
                f"GARCH requires 0 <= alpha < 1, 0 <= beta < 1, alpha + beta < 1 "
                f"(got alpha={alpha}, beta={beta})"
            )
        self.alpha = alpha
        self.beta = beta
        # Auto-derive omega so long-run monthly variance ≈ (initial_vol/sqrt(12))^2
        target_monthly_var = (self.initial_vol / np.sqrt(12)) ** 2
        self.omega = (
            omega if omega is not None
            else target_monthly_var * (1 - alpha - beta)
        )
        self.n_assets = len(mean_returns)
        # Cholesky for cross-asset correlation
        corr = correlation if correlation is not None else np.eye(self.n_assets)
        self.L = np.linalg.cholesky(np.asarray(corr, dtype=float))
        self._rng = np.random.default_rng(seed)

    def set_seed(self, seed: int | None) -> None:
        self._rng = np.random.default_rng(seed)

    def generate_path(
        self, n_years: int, n_sims: int
    ) -> np.ndarray:
        """Generate GARCH-filtered return paths with cross-asset correlation."""
        n_months = n_years * 12
        monthly_mean = self.mean / 12
        monthly_vol = self.initial_vol / np.sqrt(12)

        returns = np.zeros((n_sims, n_months, self.n_assets))
        sigma2 = np.zeros((n_sims, n_months, self.n_assets))
        # Initialize variance at long-run level
        sigma2[:, 0, :] = monthly_vol ** 2
        # omega broadcast per asset (support scalar or array)
        omega_arr = np.broadcast_to(self.omega, (self.n_assets,))

        for t in range(n_months):
            if t > 0:
                prev_ret_sq = (returns[:, t - 1, :] - monthly_mean) ** 2
                sigma2[:, t, :] = (
                    omega_arr
                    + self.alpha * prev_ret_sq
                    + self.beta * sigma2[:, t - 1, :]
                )

            sigma = np.sqrt(np.maximum(sigma2[:, t, :], 1e-12))
            # Correlated standard-normal draws
            z = self._rng.standard_normal((n_sims, self.n_assets))
            correlated_z = z @ self.L.T
            returns[:, t, :] = correlated_z * sigma + monthly_mean

        return returns

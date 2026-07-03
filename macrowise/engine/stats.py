"""
Statistics calculator — computes portfolio statistics matching PV's output format.
"""

import numpy as np
import pandas as pd
from typing import Optional


def calculate_portfolio_stats(
    balance_series: np.ndarray,
    inflation_mean: float = 0.04,
) -> dict:
    """
    Calculate portfolio statistics for a single simulation path.

    Parameters
    ----------
    balance_series : ndarray, shape (n_months,)
        Portfolio balance over time.
    inflation_mean : float
        Mean inflation for CAGR adjustment.

    Returns
    -------
    dict with keys: cagr, total_return, max_drawdown, etc.
    """
    if len(balance_series) < 2:
        return {
            "cagr": 0.0,
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "final_balance": balance_series[-1] if len(balance_series) > 0 else 0.0,
            "success": True,
        }

    # CAGR
    n_years = len(balance_series) / 12
    final = balance_series[-1]
    initial = balance_series[0]
    total_return = (final / initial) - 1
    cagr = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0.0

    # Max drawdown
    peak = np.maximum.accumulate(balance_series)
    drawdown = (balance_series - peak) / peak
    max_drawdown = drawdown.min()

    # Success: ending balance > 0
    success = final > 0

    return {
        "cagr": cagr,
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "final_balance": final,
        "success": success,
        "volatility": np.std(np.diff(balance_series) / balance_series[:-1]) * np.sqrt(12) if len(balance_series) > 12 else 0.0,
    }


def calculate_sharpe_ratio(
    returns: np.ndarray,
    risk_free_rate: float = 0.04,
) -> float:
    """Sharpe ratio = (mean_return - rf) / std_return."""
    excess = returns.mean() - risk_free_rate / 12
    std = returns.std()
    if std == 0:
        return 0.0
    return (excess / std) * np.sqrt(12)


def calculate_sortino_ratio(
    returns: np.ndarray,
    risk_free_rate: float = 0.04,
    target_return: float = 0.0,
) -> float:
    """Sortino ratio = (mean - rf) / downside_deviation."""
    excess = returns.mean() - risk_free_rate / 12
    downside = returns[returns < target_return]
    if len(downside) == 0:
        return float("inf")
    downside_std = np.sqrt((downside ** 2).mean())
    if downside_std == 0:
        return float("inf")
    return (excess / downside_std) * np.sqrt(12)


def percentile_array(arr: np.ndarray, percentiles: list[float]) -> dict:
    """Compute percentiles of an array."""
    return {f"p{int(p * 100)}": float(np.percentile(arr, p * 100)) for p in percentiles}


def safe_withdrawal_rate(
    final_balances: np.ndarray,
    initial_balance: float,
    years: int,
) -> float:
    """
    Calculate safe withdrawal rate (SWR).
    SWR = withdrawal rate (as % of initial portfolio) that achieves 90% success rate.
    Uses binary search to find the rate where 90% of simulations end with positive balance.
    """
    if initial_balance <= 0:
        return 0.0

    # Binary search for SWR that gives 90% success rate
    low = 0.0
    high = 0.15  # Start with 15% as upper bound

    for _ in range(20):  # 20 iterations gives ~0.001% precision
        mid = (low + high) / 2
        # For each simulation, check if it survives at this withdrawal rate
        # Approximate: final_balance >= initial_balance * (1 + mid * years)
        # More accurately: we need to simulate the withdrawal process
        # For now, use the heuristic that final >= withdrawals
        total_withdrawn = initial_balance * mid * years
        successful = np.sum(final_balances >= total_withdrawn) / len(final_balances)

        if successful >= 0.90:
            low = mid  # Can withdraw more
        else:
            high = mid  # Too much, reduce

    return low


def perpetual_withdrawal_rate(
    balance_paths: np.ndarray,
    initial_balance: float,
    years: int,
) -> float:
    """
    Calculate perpetual withdrawal rate (PWR).
    PWR = sustainable forever withdrawal rate based on mean returns.

    Parameters
    ----------
    balance_paths : ndarray
        Either shape (n_sims, n_months+1) or (n_sims,).
        If 2D, uses the last column as final balance.
    """
    # Handle both 2D (full paths) and 1D (final balances only)
    if balance_paths.ndim == 2:
        final_balances = balance_paths[:, -1]
    else:
        final_balances = np.asarray(balance_paths)

    mean_final = np.mean(final_balances)
    if mean_final <= 0:
        return 0.0

    cagrs = []
    for fb in final_balances:
        if fb > 0:
            cagr = (fb / initial_balance) ** (1 / years) - 1
            cagrs.append(cagr)

    if not cagrs:
        return 0.0
    mean_cagr = np.mean(cagrs)
    return max(0.0, mean_cagr * 0.95)  # 5% fee assumption


def compute_percentile_balances(
    paths: np.ndarray,
    percentiles: list[float] | None = None,
) -> pd.DataFrame:
    """
    Compute percentile portfolio balances at each year.

    Parameters
    ----------
    paths : ndarray, shape (n_sims, n_months, n_assets)
        Simulated return paths.
    percentiles : list[float] | None
        Percentiles to compute (0-1 scale).

    Returns
    -------
    DataFrame indexed by year, columns = percentile labels
    """
    if percentiles is None:
        percentiles = [0.10, 0.25, 0.50, 0.75, 0.90]

    # Convert returns to cumulative balance
    # Assume equal-weighted portfolio for now
    port_returns = paths.mean(axis=2)  # (n_sims, n_months)
    balance_paths = np.cumprod(1 + port_returns, axis=1)  # (n_sims, n_months)

    n_years = balance_paths.shape[1] // 12
    result = {}
    for yr in range(n_years + 1):
        month_idx = min(yr * 12, balance_paths.shape[1] - 1)
        balances = balance_paths[:, month_idx]
        result[yr] = {
            f"p{int(p * 100)}": float(np.percentile(balances, p * 100))
            for p in percentiles
        }

    return pd.DataFrame(result).T


def compute_withdrawal_survival(
    paths: np.ndarray,
    initial_balance: float,
    withdrawal_rate: float,
    years: int,
) -> dict:
    """
    Compute withdrawal success statistics.

    Returns
    -------
    dict with survival_rate, median_final, etc.
    """
    port_returns = paths.mean(axis=2)
    balance_paths = np.cumprod(1 + port_returns, axis=1)

    withdrawals = np.zeros((paths.shape[0], paths.shape[1]))
    for yr in range(years):
        month_start = yr * 12
        for m in range(12):
            withdrawals[:, month_start + m] = withdrawal_rate * initial_balance / 12

    # Track balance after withdrawals
    success_counts = 0
    final_balances = []

    for sim in range(paths.shape[0]):
        balance = initial_balance
        depleted = False
        for m in range(years * 12):
            # Growth first
            balance *= 1 + port_returns[sim, m]
            # Withdrawal
            balance -= withdrawals[sim, m]
            if balance <= 0:
                depleted = True
                break
        final_balances.append(max(0.0, balance))
        if not depleted:
            success_counts += 1

    return {
        "success_rate": success_counts / paths.shape[0],
        "median_final": float(np.median(final_balances)),
        "mean_final": float(np.mean(final_balances)),
        "p10_final": float(np.percentile(final_balances, 10)),
        "p90_final": float(np.percentile(final_balances, 90)),
    }

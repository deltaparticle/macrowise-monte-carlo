"""Statistics calculator — portfolio metrics matching PV's output format."""

import numpy as np
import pandas as pd


def calculate_portfolio_stats(
    balance_series: np.ndarray,
    inflation_mean: float = 0.04,
) -> dict:
    """Portfolio statistics for a single simulation path."""
    if len(balance_series) < 2 or balance_series[0] <= 0:
        return {
            "cagr": 0.0,
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "final_balance": float(balance_series[-1]) if len(balance_series) > 0 else 0.0,
            "success": True,
            "volatility": 0.0,
        }

    n_years = len(balance_series) / 12
    final = balance_series[-1]
    initial = balance_series[0]
    total_return = (final / initial) - 1
    cagr = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0.0

    peak = np.maximum.accumulate(balance_series)
    drawdown = (balance_series - peak) / np.maximum(peak, 1e-9)
    max_drawdown = float(drawdown.min())

    # Volatility: use returns of positive-only balance segments
    safe_bal = np.maximum(balance_series[:-1], 1.0)
    returns = np.diff(balance_series) / safe_bal
    vol = float(np.std(returns) * np.sqrt(12)) if len(returns) > 12 else 0.0

    return {
        "cagr": cagr,
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "final_balance": float(final),
        "success": final > initial * 0.01,
        "volatility": vol,
    }


def calculate_sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.04) -> float:
    """Sharpe ratio = (mean_return - rf) / std_return, annualized."""
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
    """Sortino ratio = (mean - rf) / target-downside-deviation, annualized.

    Uses standard TDD formula: sqrt(mean(max(0, target-r)^2)) over ALL observations.
    """
    excess = returns.mean() - risk_free_rate / 12
    downside = np.maximum(0.0, target_return - returns)
    downside_std = np.sqrt((downside ** 2).mean())
    if downside_std == 0:
        return float("nan")
    return (excess / downside_std) * np.sqrt(12)


def percentile_array(arr: np.ndarray, percentiles: list[float]) -> dict:
    return {f"p{int(p * 100)}": float(np.percentile(arr, p * 100)) for p in percentiles}


# ─────────────────────────────────────────────────────────────────────
# Safe Withdrawal Rate — real Monte Carlo calc
# ─────────────────────────────────────────────────────────────────────

def safe_withdrawal_rate(
    port_returns: np.ndarray,
    initial_balance: float,
    years: int,
    inflation_mean: float = 0.04,
    survival_threshold: float = 0.95,
    survival_floor_frac: float = 0.01,
) -> float:
    """Real Monte Carlo Safe Withdrawal Rate.

    For each candidate annual withdrawal rate (0.5% to 15% in 0.25% steps),
    simulate the portfolio with an inflation-adjusted monthly withdrawal and
    count how many paths survive N years. SWR = highest rate where at least
    `survival_threshold` fraction of paths keep balance above
    `initial_balance * survival_floor_frac` throughout the horizon.

    Parameters
    ----------
    port_returns : ndarray, shape (n_sims, n_months)
        Monthly portfolio returns per simulation (already weighted by allocs).
    initial_balance : float
    years : int
    inflation_mean : float
        Annual inflation used to grow withdrawal amount over time.
    survival_threshold : float
        Fraction of paths that must survive (default 0.95).
    survival_floor_frac : float
        Balance floor as fraction of initial (default 1%).
    """
    if initial_balance <= 0 or years <= 0:
        return 0.0
    if port_returns.ndim != 2:
        return 0.0

    n_sims, n_months = port_returns.shape
    rates = np.arange(0.005, 0.155, 0.0025)  # 0.5% to 15%, 0.25% steps

    # Precompute inflation multiplier per month
    infl_per_month = (1 + inflation_mean) ** (np.arange(n_months) / 12)
    floor = initial_balance * survival_floor_frac

    best_rate = 0.0
    for rate in rates:
        # Monthly withdrawal at t=0: rate * initial_balance / 12
        base_wd = rate * initial_balance / 12
        wd_schedule = base_wd * infl_per_month  # (n_months,)

        balances = np.full(n_sims, initial_balance, dtype=np.float64)
        survived = np.ones(n_sims, dtype=bool)
        for m in range(n_months):
            balances = balances * (1 + port_returns[:, m]) - wd_schedule[m]
            balances = np.maximum(balances, 0.0)
            survived &= balances > floor

        if survived.mean() >= survival_threshold:
            best_rate = float(rate)
        else:
            break  # Higher rates will only be worse
    return best_rate


def perpetual_withdrawal_rate(
    port_returns: np.ndarray,
    initial_balance: float,
    years: int,
    inflation_mean: float = 0.04,
    survival_threshold: float = 0.95,
) -> float:
    """Perpetual Withdrawal Rate — highest rate where the median final balance
    is at least the initial balance in nominal terms (so the portfolio can
    perpetuate indefinitely at this withdrawal rate).
    """
    if initial_balance <= 0 or years <= 0 or port_returns.ndim != 2:
        return 0.0

    n_sims, n_months = port_returns.shape
    rates = np.arange(0.005, 0.155, 0.0025)
    infl_per_month = (1 + inflation_mean) ** (np.arange(n_months) / 12)

    best_rate = 0.0
    for rate in rates:
        base_wd = rate * initial_balance / 12
        wd_schedule = base_wd * infl_per_month

        balances = np.full(n_sims, initial_balance, dtype=np.float64)
        for m in range(n_months):
            balances = balances * (1 + port_returns[:, m]) - wd_schedule[m]
            balances = np.maximum(balances, 0.0)

        # Perpetual condition: median final ≥ initial (nominal)
        # AND survival ≥ threshold
        survival = (balances > initial_balance * 0.01).mean()
        median_final = np.median(balances)
        if median_final >= initial_balance and survival >= survival_threshold:
            best_rate = float(rate)
        else:
            break
    return best_rate


def compute_percentile_balances(
    paths: np.ndarray,
    percentiles: list[float] | None = None,
) -> pd.DataFrame:
    """Percentile portfolio balance table."""
    if percentiles is None:
        percentiles = [0.10, 0.25, 0.50, 0.75, 0.90]

    port_returns = paths.mean(axis=2)  # Equal-weight fallback
    balance_paths = np.cumprod(1 + port_returns, axis=1)

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
    port_returns: np.ndarray,
    initial_balance: float,
    withdrawal_rate: float,
    years: int,
    inflation_mean: float = 0.04,
) -> dict:
    """Withdrawal survival stats — respects actual portfolio returns.

    Parameters
    ----------
    port_returns : ndarray, shape (n_sims, n_months)
        Monthly portfolio returns (already weighted).
    """
    n_sims, n_months = port_returns.shape
    infl_per_month = (1 + inflation_mean) ** (np.arange(n_months) / 12)
    base_wd = withdrawal_rate * initial_balance / 12
    wd_schedule = base_wd * infl_per_month

    balances = np.full(n_sims, initial_balance, dtype=np.float64)
    survived = np.ones(n_sims, dtype=bool)
    for m in range(n_months):
        balances = balances * (1 + port_returns[:, m]) - wd_schedule[m]
        balances = np.maximum(balances, 0.0)
        survived &= balances > initial_balance * 0.01

    return {
        "success_rate": float(survived.mean()),
        "median_final": float(np.median(balances)),
        "mean_final": float(np.mean(balances)),
        "p10_final": float(np.percentile(balances, 10)),
        "p90_final": float(np.percentile(balances, 90)),
    }

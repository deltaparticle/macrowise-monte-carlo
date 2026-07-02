"""
Visualization module — charts matching PortfolioVisualizer's output.

Includes:
  - Portfolio allocation pie chart
  - Balance percentile chart (growth of portfolio)
  - Terminal distribution histogram
  - Year-by-year percentile table
  - Performance summary table
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from typing import Optional


# Indian-friendly fonts
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.titlesize"] = 12
plt.rcParams["axes.labelsize"] = 10
plt.rcParams["figure.dpi"] = 100


def format_inr(value: float, lakh_crore: bool = True) -> str:
    """Format a number in Indian numbering system (Lakh/Crore)."""
    if value >= 1e7:  # Crore
        return f"₹{value / 1e7:.1f}Cr"
    elif value >= 1e5:  # Lakh
        return f"₹{value / 1e5:.1f}L"
    elif value >= 1e3:
        return f"₹{value / 1e3:.0f}K"
    else:
        return f"₹{value:.0f}"


def plot_allocation_pie(
    names: list[str],
    allocations: list[float],
    title: str = "Portfolio Allocation",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Portfolio allocation pie chart (PV's first chart).

    Parameters
    ----------
    names : list[str]
        Asset names.
    allocations : list[float]
        Allocation percentages (should sum to 1).
    title : str
        Chart title.
    save_path : str | None
        If provided, save to this file path.

    Returns
    -------
    matplotlib Figure
    """
    fig, ax = plt.subplots(figsize=(6, 4))
    colors = plt.cm.Set3(np.linspace(0, 1, len(names)))
    wedges, texts, autotexts = ax.pie(
        allocations,
        labels=names,
        autopct="%1.0f%%",
        colors=colors,
        startangle=90,
        wedgeprops=dict(edgecolor="white", linewidth=2),
    )
    for at in autotexts:
        at.set_fontsize(9)
    ax.set_title(title, fontsize=12, fontweight="bold")
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_balance_chart(
    balance_percentiles: pd.DataFrame,
    title: str = "Portfolio Balance Over Time",
    currency: str = "INR",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Portfolio balance percentile chart (PV's Growth chart).

    Shows 10th, 25th, 50th, 75th, 90th percentile balance paths.

    Parameters
    ----------
    balance_percentiles : DataFrame
        Year-by-year percentile table from MonteCarloResults.
    title : str
        Chart title.
    currency : str
        Currency label.
    save_path : str | None
        If provided, save to this file path.

    Returns
    -------
    matplotlib Figure
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    years = balance_percentiles.index.values
    percentile_cols = [c for c in balance_percentiles.columns if c.startswith("p")]
    percentile_cols.sort()

    colors = {
        "p10": "#e74c3c",
        "p25": "#e67e22",
        "p50": "#2c3e50",
        "p75": "#27ae60",
        "p90": "#2980b9",
    }

    fill_colors = {
        "p10": "#fadbd8",
        "p25": "#fdebd0",
        "p50": "#d5dbdb",
        "p75": "#d5f5e3",
        "p90": "#d6eaf8",
    }

    # Fill between percentile bands
    if "p10" in balance_percentiles.columns and "p90" in balance_percentiles.columns:
        ax.fill_between(
            years,
            balance_percentiles["p10"],
            balance_percentiles["p90"],
            alpha=0.2,
            color=fill_colors.get("p10", "gray"),
            label="10th-90th",
        )

    if "p25" in balance_percentiles.columns and "p75" in balance_percentiles.columns:
        ax.fill_between(
            years,
            balance_percentiles["p25"],
            balance_percentiles["p75"],
            alpha=0.3,
            color=fill_colors.get("p25", "gray"),
            label="25th-75th",
        )

    # Plot percentile lines
    for col in percentile_cols:
        if col in balance_percentiles.columns:
            label_name = f"{int(col[1:])}th Percentile"
            ax.plot(
                years,
                balance_percentiles[col],
                color=colors.get(col, "gray"),
                linewidth=2 if col == "p50" else 1.5,
                linestyle="-" if col == "p50" else "--",
                label=label_name,
                zorder=5,
            )

    ax.set_xlabel("Years", fontsize=11)
    ax.set_ylabel(f"Portfolio Balance ({currency})", fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: format_inr(x)))

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_terminal_distribution(
    final_balances: np.ndarray,
    title: str = "Terminal Portfolio Balance Distribution",
    currency: str = "INR",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Terminal balance histogram (PV's End Balance Histogram).

    Parameters
    ----------
    final_balances : ndarray
        Final balances across all simulations.
    title : str
        Chart title.
    currency : str
        Currency label.
    save_path : str | None
        If provided, save to this file path.

    Returns
    -------
    matplotlib Figure
    """
    fig, ax = plt.subplots(figsize=(10, 5))

    # Filter outliers (top/bottom 1%)
    p1, p99 = np.percentile(final_balances, [1, 99])
    filtered = final_balances[(final_balances >= p1) & (final_balances <= p99)]

    ax.hist(
        filtered,
        bins=50,
        color="#3498db",
        alpha=0.7,
        edgecolor="white",
        linewidth=0.5,
    )

    # Mark percentiles
    for pct, label, color in [
        (10, "10th", "#e74c3c"),
        (25, "25th", "#e67e22"),
        (50, "50th", "#2c3e50"),
        (75, "75th", "#27ae60"),
        (90, "90th", "#2980b9"),
    ]:
        val = np.percentile(final_balances, pct * 100)
        ax.axvline(val, color=color, linestyle="--", linewidth=1.5, alpha=0.8)
        ax.text(
            val, ax.get_ylim()[1] * 0.9 if ax.get_ylim()[1] > 0 else 0.9,
            f"  {label}\n  {format_inr(val)}",
            color=color,
            fontsize=8,
            va="top",
        )

    ax.set_xlabel(f"Terminal Balance ({currency})", fontsize=11)
    ax.set_ylabel("Frequency", fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: format_inr(x)))

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_drawdown_distribution(
    max_drawdowns: np.ndarray,
    title: str = "Maximum Drawdown Distribution",
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Histogram of maximum drawdowns across simulations."""
    fig, ax = plt.subplots(figsize=(10, 5))

    ax.hist(
        max_drawdowns * 100,
        bins=50,
        color="#e74c3c",
        alpha=0.7,
        edgecolor="white",
    )

    median_dd = np.median(max_drawdowns) * 100
    ax.axvline(median_dd, color="#2c3e50", linestyle="--", linewidth=2,
               label=f"Median: {median_dd:.1f}%")
    ax.axvline(0, color="black", linestyle="-", linewidth=1, alpha=0.3)

    ax.set_xlabel("Maximum Drawdown (%)", fontsize=11)
    ax.set_ylabel("Frequency", fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.legend()

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig

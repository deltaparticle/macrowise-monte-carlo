"""
Glide Path — linear interpolation between two portfolio allocations.

PV's Financial Goals uses a glide path to transition from a career-stage
portfolio (aggressive) to a retirement-stage portfolio (conservative)
over a specified number of years.
"""

import numpy as np
from typing import List, Tuple


def linear_glide_path(
    start_allocations: List[Tuple[str, float]],
    end_allocations: List[Tuple[str, float]],
    glide_path_years: int,
) -> List[List[Tuple[str, float]]]:
    """
    Generate a linear glide path between two portfolios.

    Parameters
    ----------
    start_allocations : list of (asset_code, weight)
        Starting portfolio (career stage).
    end_allocations : list of (asset_code, weight)
        Ending portfolio (retirement stage).
    glide_path_years : int
        Number of years for the transition.

    Returns
    -------
    list of length glide_path_years + 1
        Each element is a list of (asset_code, weight) for that year.
        Year 0 = start_allocations, Year glide_path_years = end_allocations.
    """
    # Build union of all assets
    start_dict = {asset: weight for asset, weight in start_allocations}
    end_dict = {asset: weight for asset, weight in end_allocations}
    all_assets = sorted(set(start_dict.keys()) | set(end_dict.keys()))

    path = []
    for year in range(glide_path_years + 1):
        t = glide_path_years if glide_path_years > 0 else 1
        frac = year / t  # 0.0 to 1.0
        year_alloc = []
        for asset in all_assets:
            start_w = start_dict.get(asset, 0.0)
            end_w = end_dict.get(asset, 0.0)
            weight = start_w + (end_w - start_w) * frac
            year_alloc.append((asset, weight))
        path.append(year_alloc)

    return path


def apply_glide_path_to_returns(
    return_paths: np.ndarray,
    start_allocations: List[Tuple[str, float]],
    end_allocations: List[Tuple[str, float]],
    glide_path_years: int,
    career_years: int,
) -> np.ndarray:
    """
    Apply glide path to return paths.

    Parameters
    ----------
    return_paths : ndarray, shape (n_sims, n_months, n_assets)
        Simulated returns for each asset.
    start_allocations : list of (asset_code, weight)
        Starting portfolio.
    end_allocations : list of (asset_code, weight)
        Ending portfolio.
    glide_path_years : int
        Years for transition.
    career_years : int
        Total career years (before retirement starts).

    Returns
    -------
    ndarray, shape (n_sims, n_months)
        Portfolio returns after applying glide path.
    """
    n_sims, n_months, n_assets = return_paths.shape
    glide_months = glide_path_years * 12

    # Build asset index map
    asset_codes = [a for a, _ in start_allocations]
    start_weights = np.array([w for _, w in start_allocations])
    end_weights = np.array([w for _, w in end_allocations])

    # Portfolio returns with start weights
    port_rets_start = return_paths @ start_weights
    port_rets_end = return_paths @ end_weights

    result = np.zeros((n_sims, n_months))

    for sim in range(n_sims):
        for m in range(n_months):
            if m < career_years * 12:
                # Career phase
                if m < glide_months:
                    # In glide path
                    t = m / glide_months if glide_months > 0 else 1.0
                    weight = 1.0 - t
                    result[sim, m] = weight * port_rets_start[sim, m] + (1 - weight) * port_rets_end[sim, m]
                else:
                    result[sim, m] = port_rets_start[sim, m]
            else:
                # Retirement phase
                retirement_month = m - career_years * 12
                if retirement_month < glide_months:
                    t = retirement_month / glide_months if glide_months > 0 else 1.0
                    weight = 1.0 - t
                    result[sim, m] = weight * port_rets_start[sim, m] + (1 - weight) * port_rets_end[sim, m]
                else:
                    result[sim, m] = port_rets_end[sim, m]

    return result

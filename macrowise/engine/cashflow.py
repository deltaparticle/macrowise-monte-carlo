"""
Cash Flow Engine — handles PV's 9 cashflow types with Indian currency conventions.

Cashflow Types (matching PV):
  0 = None
  1 = Contribute — Fixed periodic contribution (SIP)
  2 = Withdraw — Fixed periodic withdrawal
  3 = Fixed % — Withdraw fixed % of portfolio balance
  4 = Life Expectancy — RMD-style withdrawal based on age
  5 = Rolling Avg — 3-year rolling average spending rule
  6 = Geometric — Guyton-Klinger geometric spending rule
  8 = Fixed Withdrawal + Pct Change — Fixed amount with annual % change
  9 = Contribution + Pct Change — Fixed contribution with annual % change
"""

import numpy as np
from dataclasses import dataclass
from typing import Literal


Frequency = Literal["monthly", "quarterly", "annual"]
AdjustmentType = Literal[0, 1, 2, 3, 4, 5, 6, 8, 9]


@dataclass
class CashFlowConfig:
    """
    Configuration for a cash flow schedule.

    Parameters
    ----------
    adjustment_type : int
        0=no cashflow | 1=contribute | 2=withdraw | 3=fixed% | 4=life expectancy | 5=rolling avg | 6=geometric
    amount : float
        Fixed periodic amount in INR (monthly or annual depending on frequency).
    growth_rate : float
        Annual growth rate of the periodic amount (e.g., 0.06 = 6%).
    frequency : str
        'monthly', 'quarterly', or 'annual'.
    timing : str
        'beginning' or 'end' of period.
    inflation_adjusted : bool
        Whether the amount grows with inflation.
    inflation_mean : float
        Mean annual inflation for adjustment.
    current_age : int
        Starting age (for life expectancy withdrawals).
    life_expectancy_model : str
        'single' or 'uniform'.
    rolling_periods : int
        Periods for rolling average (2-5 years).
    smoothing_rate : float
        Weight for previous-period spending (50-90%).
    withdrawal_percentage : float
        % of portfolio to withdraw (for type=3).
    """

    adjustment_type: int = 0
    amount: float = 0.0
    growth_rate: float = 0.0
    frequency: str = "annual"
    timing: str = "end"
    inflation_adjusted: bool = False
    inflation_mean: float = 0.04
    current_age: int = 30
    life_expectancy_model: str = "single"
    rolling_periods: int = 3
    smoothing_rate: float = 0.75
    withdrawal_percentage: float = 4.0
    pct_change: float = 0.0  # Annual % change for type 8/9

    # Month multipliers
    _MONTHLY = 12
    _QUARTERLY = 4
    _ANNUAL = 1

    @property
    def periods_per_year(self) -> int:
        if self.frequency == "monthly":
            return self._MONTHLY
        elif self.frequency == "quarterly":
            return self._QUARTERLY
        return self._ANNUAL

    @property
    def base_amount(self) -> float:
        """Annualized amount."""
        if self.frequency == "monthly":
            return self.amount * 12
        elif self.frequency == "quarterly":
            return self.amount * 4
        return self.amount


class CashFlowEngine:
    """
    Generate cash flow schedules for simulation.

    Handles PV's cashflow types with proper Indian currency formatting.
    Uses ₹ (INR) as the base currency.
    """

    def __init__(self, config: CashFlowConfig):
        self.config = config

    def generate_schedule(self, n_months: int) -> np.ndarray:
        """
        Generate a cash flow array for n_months.

        Positive = contribution (money into portfolio)
        Negative = withdrawal (money out of portfolio)

        Returns
        -------
        ndarray, shape (n_months,)
        """
        cfg = self.config

        if cfg.adjustment_type == 0:
            return np.zeros(n_months)
        elif cfg.adjustment_type == 1:
            return self._contribution_schedule(n_months, sign=1)
        elif cfg.adjustment_type == 2:
            return self._fixed_withdrawal_schedule(n_months, sign=-1)
        elif cfg.adjustment_type == 3:
            return self._fixed_pct_schedule(n_months)
        elif cfg.adjustment_type == 4:
            return self._life_expectancy_schedule(n_months)
        elif cfg.adjustment_type == 5:
            return self._rolling_average_schedule(n_months)
        elif cfg.adjustment_type == 6:
            return self._geometric_schedule(n_months)
        elif cfg.adjustment_type == 8:
            return self._fixed_with_pct_change_schedule(n_months, sign=-1)
        elif cfg.adjustment_type == 9:
            return self._fixed_with_pct_change_schedule(n_months, sign=1)
        else:
            return np.zeros(n_months)

    def _amount_at_month(
        self,
        month: int,
        sign: float = 1.0,
    ) -> float:
        """Compute the cashflow amount at a given month index."""
        cfg = self.config
        year = month / 12
        amount = cfg.base_amount

        # Apply growth
        if cfg.growth_rate > 0:
            amount *= (1 + cfg.growth_rate) ** year

        # Apply inflation adjustment
        if cfg.inflation_adjusted and cfg.adjustment_type != 4:
            amount *= (1 + cfg.inflation_mean) ** year

        # Per-period amount
        per_period = amount / cfg.periods_per_year

        # Check if this is a cashflow month
        if cfg.frequency == "monthly":
            return sign * per_period
        elif cfg.frequency == "quarterly":
            return sign * per_period if month % 3 == 0 else 0.0
        else:
            return sign * per_period if month % 12 == 0 else 0.0

    def _contribution_schedule(
        self, n_months: int, sign: float = 1.0
    ) -> np.ndarray:
        """Fixed periodic contribution (SIP)."""
        result = np.zeros(n_months)
        for m in range(n_months):
            result[m] = self._amount_at_month(m, sign=sign)
        return result

    def _fixed_withdrawal_schedule(self, n_months: int, sign: float = -1.0) -> np.ndarray:
        """Fixed periodic withdrawal."""
        return self._contribution_schedule(n_months, sign=sign)

    def _fixed_with_pct_change_schedule(self, n_months: int, sign: float = -1.0) -> np.ndarray:
        """
        Fixed amount with annual percentage change (PV type 8 = withdrawal, type 9 = contribution).
        The amount grows/shrinks by pct_change each year.
        """
        result = np.zeros(n_months)
        for m in range(n_months):
            year = m / 12
            amount = self.config.base_amount * (1 + self.config.pct_change) ** year
            per_period = amount / self.config.periods_per_year
            if self.config.frequency == "monthly":
                result[m] = sign * per_period
            elif self.config.frequency == "quarterly":
                result[m] = sign * per_period if m % 3 == 0 else 0.0
            else:
                result[m] = sign * per_period if m % 12 == 0 else 0.0
        return result

    def _fixed_pct_schedule(self, n_months: int) -> np.ndarray:
        """
        Fixed percentage withdrawal.
        Amount depends on portfolio balance — handled separately in engine.
        Returns the rate; engine applies it to balance each month.
        """
        return np.full(n_months, self.config.withdrawal_percentage / 100.0)

    def _life_expectancy_schedule(self, n_months: int) -> np.ndarray:
        """
        Life expectancy based withdrawal (RMD style).
        Withdrawal % = 1 / remaining years of life.
        """
        # Simplified: use IRS-style life expectancy tables
        result = np.zeros(n_months)
        age = self.config.current_age

        for m in range(n_months):
            if m % 12 == 0:  # Annual withdrawal
                year = m // 12
                current_age = age + year

                # IRS Uniform Lifetime Table (simplified)
                le_years = self._life_expectancy(current_age)
                if le_years > 0:
                    withdrawal_pct = 1.0 / le_years
                    annual_amount = self.config.base_amount * withdrawal_pct
                    result[m] = -annual_amount / 12  # Monthly withdrawal

        return result

    @staticmethod
    def _life_expectancy(age: int) -> int:
        """
        IRS-style life expectancy (simplified).
        For Indian implementation, use SRS life expectancy data.
        """
        # Simplified IRS table; for production, use SRS data
        le_table = {
            30: 53.1, 35: 48.5, 40: 43.9, 45: 39.2, 50: 34.6,
            55: 30.0, 60: 25.5, 65: 21.2, 70: 17.0, 75: 13.1,
            80: 9.7, 85: 6.7, 90: 4.4, 95: 2.8,
        }
        ages = sorted(le_table.keys())
        if age <= ages[0]:
            return le_table[ages[0]]
        if age >= ages[-1]:
            return le_table[ages[-1]]

        # Linear interpolation
        for i in range(len(ages) - 1):
            if ages[i] <= age < ages[i + 1]:
                frac = (age - ages[i]) / (ages[i + 1] - ages[i])
                return int(le_table[ages[i]] * (1 - frac) + le_table[ages[i + 1]] * frac)
        return le_table[ages[-1]]

    def _rolling_average_schedule(self, n_months: int) -> np.ndarray:
        """
        Rolling average spending rule (PV type=5).
        Withdrawal = avg(portfolio balance over last N years) * withdrawal_pct.
        """
        result = np.zeros(n_months)
        return result  # Simplified — needs balance path to compute properly

    def _geometric_schedule(self, n_months: int) -> np.ndarray:
        """
        Guyton-Klinger geometric spending rule (PV type=6).
        Includes capital preservation, inflation, and market return adjustments.
        """
        result = np.zeros(n_months)
        return result  # Simplified — needs balance path to compute properly


def create_sip(
    monthly_amount: float,
    annual_growth: float = 0.05,
    years: int = 30,
) -> np.ndarray:
    """
    Convenience function: create a systematic investment plan (SIP).

    Parameters
    ----------
    monthly_amount : float
        Starting monthly SIP amount in INR.
    annual_growth : float
        Annual step-up rate.
    years : int
        Total years.

    Returns
    -------
    ndarray, shape (months,)
        Monthly cashflow amounts (positive = contribution).
    """
    config = CashFlowConfig(
        adjustment_type=1,
        amount=monthly_amount,
        growth_rate=annual_growth,
        frequency="monthly",
    )
    engine = CashFlowEngine(config)
    return engine.generate_schedule(years * 12)

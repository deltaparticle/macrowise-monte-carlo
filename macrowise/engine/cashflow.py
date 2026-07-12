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
AdjustmentType = Literal[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]  # 7 reserved for future use


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
        """Compute the cashflow amount at a given month index.

        Honors `timing` ('beginning' vs 'end' of period). 'end' fires at
        m == step-1 mod step; 'beginning' fires at m == 0 mod step.
        """
        cfg = self.config
        year = month / 12
        amount = cfg.base_amount

        if cfg.growth_rate > 0:
            amount *= (1 + cfg.growth_rate) ** year

        if cfg.inflation_adjusted and cfg.adjustment_type != 4:
            amount *= (1 + cfg.inflation_mean) ** year

        per_period = amount / cfg.periods_per_year

        # Determine step size and offset per frequency + timing
        step_map = {"monthly": 1, "quarterly": 3, "annual": 12}
        step = step_map.get(cfg.frequency, 12)
        offset = 0 if cfg.timing == "beginning" else (step - 1)

        if step == 1:
            return sign * per_period
        if month % step == offset:
            return sign * per_period
        return 0.0

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
        """Fixed amount with annual % change (PV type 8 = withdrawal, type 9 = contribution).

        Honors `inflation_adjusted` and `timing` like other schedule methods.
        """
        cfg = self.config
        result = np.zeros(n_months)
        step_map = {"monthly": 1, "quarterly": 3, "annual": 12}
        step = step_map.get(cfg.frequency, 12)
        offset = 0 if cfg.timing == "beginning" else (step - 1)

        for m in range(n_months):
            year = m / 12
            amount = cfg.base_amount * (1 + cfg.pct_change) ** year
            if cfg.inflation_adjusted:
                amount *= (1 + cfg.inflation_mean) ** year
            per_period = amount / cfg.periods_per_year
            if step == 1 or m % step == offset:
                result[m] = sign * per_period
        return result

    def _fixed_pct_schedule(self, n_months: int) -> np.ndarray:
        """
        Fixed percentage withdrawal.
        Amount depends on portfolio balance — handled separately in engine.
        Returns the rate; engine applies it to balance each month.
        """
        return np.full(n_months, self.config.withdrawal_percentage / 100.0)

    def _life_expectancy_schedule(self, n_months: int) -> np.ndarray:
        """Life-expectancy-based withdrawal (RMD style).

        Withdrawal% = 1 / remaining years of life.
        Annual amount = base_amount * withdrawal_pct, spread evenly across 12 months.
        """
        result = np.zeros(n_months)
        age = self.config.current_age

        current_le = self._life_expectancy(age)  # cached per year
        for m in range(n_months):
            year = m // 12
            if m % 12 == 0:
                current_age = age + year
                current_le = self._life_expectancy(current_age)
            if current_le > 0:
                monthly_amount = (self.config.base_amount / current_le) / 12
                result[m] = -monthly_amount
        return result

    @staticmethod
    def _life_expectancy(age: int) -> float:
        """IRS-style life expectancy (years remaining) — returns float."""
        le_table = {
            30: 53.1, 35: 48.5, 40: 43.9, 45: 39.2, 50: 34.6,
            55: 30.0, 60: 25.5, 65: 21.2, 70: 17.0, 75: 13.1,
            80: 9.7, 85: 6.7, 90: 4.4, 95: 2.8,
        }
        ages = sorted(le_table.keys())
        if age <= ages[0]:
            return float(le_table[ages[0]])
        if age >= ages[-1]:
            return float(le_table[ages[-1]])
        for i in range(len(ages) - 1):
            if ages[i] <= age < ages[i + 1]:
                frac = (age - ages[i]) / (ages[i + 1] - ages[i])
                return float(le_table[ages[i]] * (1 - frac) + le_table[ages[i + 1]] * frac)
        return float(le_table[ages[-1]])

    def _rolling_average_schedule(self, n_months: int) -> np.ndarray:
        """Rolling-average spending rule (PV type=5).

        Requires balance path to compute — cannot be generated as a schedule.
        Returns zeros with a warning; the balance-loop should compute this
        dynamically. For now, unsupported.
        """
        raise NotImplementedError(
            "Cashflow type 5 (rolling average) requires balance-path-aware computation "
            "which is not currently implemented. Use type 3 (fixed %) as a substitute."
        )

    def _geometric_schedule(self, n_months: int) -> np.ndarray:
        """Guyton-Klinger geometric spending rule (PV type=6). Unsupported."""
        raise NotImplementedError(
            "Cashflow type 6 (Guyton-Klinger) requires balance-path-aware computation "
            "which is not currently implemented. Use type 8 (fixed + pct change) as a substitute."
        )


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

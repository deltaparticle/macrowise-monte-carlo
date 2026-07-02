"""
Indian Tax Calculator — handles LTCG, STCG, dividend, and capital gains taxation.

Indian Tax Rules (FY 2024-25):
  Equity:
    - LTCG (> ₹1L, held > 1 year):       10%
    - LTCG (≤ ₹1L, held > 1 year):        0%
    - STCG (held ≤ 1 year):               15%
    - Dividend:                           0% (TDS ₹5K, but no tax at hands for most)

  Debt Funds (held > 3 years):
    - Long-term capital gains:            20% with indexation
  Debt Funds (held ≤ 3 years):
    - Short-term capital gains:            Added to income, taxed at slab rate

  Liquid / Overnight:
    - Short-term (any holding):            Added to income, slab rate
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class IndianTaxRates:
    """Indian tax rates for FY 2024-25."""

    # Equity
    equity_ltcg_above_1cr: float = 0.10       # LTCG above ₹1 lakh at 10%
    equity_ltcg_below_1cr: float = 0.00       # LTCG up to ₹1 lakh at 0%
    equity_stcg: float = 0.15                 # STCG at 15%
    dividend_tax: float = 0.00                # Dividend tax (0%, TDS ₹5K only)
    dividend_tds_threshold: float = 5_000.0   # TDS deducted if div > ₹5K

    # Debt
    debt_ltcg_rate: float = 0.20              # LTCG with indexation at 20%
    debt_stcg_slab_rate: float = 0.30         # STCG added to income at highest slab

    # Liquid funds (taxed like debt)
    liquid_stcg_rate: float = 0.30            # Short-term, added to income
    liquid_ltcg_indexed: float = 0.20         # With indexation benefit

    # Surcharges (mega-rich)
    surcharge_above_10cr: float = 0.25        # 25% on tax above ₹10Cr
    surcharge_above_2cr: float = 0.15         # 15% on tax above ₹2Cr
    surcharge_above_1cr: float = 0.10         # 10% on tax above ₹1Cr
    health_education_cess: float = 0.04       # 4% cess on total tax


@dataclass
class TaxEvent:
    """A single taxable event."""
    amount: float              # Amount withdrawn / realized gain
    cost_basis: float          # Original investment amount
    holding_period_months: int # How long it was held
    asset_category: str        # equity, debt, liquid
    is_dividend: bool = False


class IndianTaxCalculator:
    """Calculate Indian taxes on investment gains."""

    def __init__(self, rates: IndianTaxRates | None = None):
        self.rates = rates or IndianTaxRates()

    def calculate_tax_on_event(self, event: TaxEvent) -> float:
        """Calculate tax for a single withdrawal / realization event."""
        if event.amount <= 0:
            return 0.0

        gain = event.amount - event.cost_basis

        if event.is_dividend:
            return self._dividend_tax(event.amount)

        if event.asset_category == "equity":
            return self._equity_capital_gains_tax(gain, event.holding_period_months)

        elif event.asset_category == "liquid":
            return self._liquid_tax(gain)

        else:  # debt, corporate bond, dynamic bond
            return self._debt_capital_gains_tax(
                gain, event.holding_period_months, event.amount
            )

    def _dividend_tax(self, dividend_amount: float) -> float:
        """Dividend taxation — 0% for most, TDS only above ₹5K."""
        if dividend_amount <= self.rates.dividend_tds_threshold:
            return 0.0
        return dividend_amount * self.rates.dividend_tax

    def _equity_capital_gains_tax(self, gain: float, holding_months: int) -> float:
        """Equity capital gains — LTCG vs STCG."""
        if gain <= 0:
            return 0.0

        if holding_months > 12:
            # LTCG
            taxable = max(0.0, gain)
            if gain > 1_00_000:
                return gain * self.rates.equity_ltcg_above_1cr
            return 0.0
        else:
            # STCG
            return gain * self.rates.equity_stcg

    def _liquid_tax(self, gain: float) -> float:
        """Liquid fund gains — short-term, added to income."""
        if gain <= 0:
            return 0.0
        return gain * self.rates.liquid_stcg_rate

    def _debt_capital_gains_tax(
        self, gain: float, holding_months: int, total_amount: float
    ) -> float:
        """Debt fund capital gains — LTCG with indexation vs STCG."""
        if gain <= 0:
            return 0.0

        if holding_months > 36:
            # Long-term with indexation
            return gain * self.rates.debt_ltcg_rate
        else:
            # Short-term — added to income
            return gain * self.rates.debt_stcg_slab_rate

    def effective_tax_rate(self, gain: float, asset_category: str) -> float:
        """Get the effective tax rate for a given gain and asset category."""
        if gain <= 0:
            return 0.0

        if asset_category == "equity":
            if gain > 1_00_000:
                return self.rates.equity_ltcg_above_1cr
            return self.rates.equity_ltcg_below_1cr
        elif asset_category == "liquid":
            return self.rates.liquid_stcg_rate
        else:  # debt
            return self.rates.debt_ltcg_rate


# Simplified rates for Python API usage
DEFAULT_TAX_RATES = {
    "equity_ltcg": 0.10,        # 10% LTCG on gains > ₹1L
    "equity_stcg": 0.15,        # 15% STCG
    "debt_ltcg": 0.20,          # 20% with indexation
    "debt_stcg": 0.30,          # 30% at slab rate
    "liquid": 0.30,             # 30% (short-term)
    "dividend": 0.00,           # 0% dividend tax
}


def get_asset_category(code: str) -> str:
    """Map asset code to tax category."""
    code_up = code.upper()

    if any(x in code_up for x in ["NIFTY", "STOCK_", "ETF_", "BSE_", "NSE_", "EQUITY"]):
        return "equity"
    elif any(x in code_up for x in ["LIQUID", "OVERNIGHT"]):
        return "liquid"
    else:
        return "debt"

"""
Pydantic request/response schemas for the Macrowise Monte Carlo API.

All numeric fields are raw floats (0.11, not "11%"). Formatting is the client's job.
"""
from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field, ConfigDict


# ── Enums ────────────────────────────────────────────────────────────────────

Model = Literal[1, 2, 3, 4]  # 1=Historical 2=Statistical 3=Parameterized 4=Forecasted
TimeSeriesModel = Literal[1, 3]  # 1=Normal 3=GARCH
BootstrapModel = Literal[0, 1, 2]  # 0=SingleMonth 1=SingleYear 2=Block
RebalanceFrequency = Literal[0, 1, 2, 3, 4]  # 0=None 1=Annual 2=Semi 3=Q 4=Monthly
InflationModel = Literal[1, 2]  # 1=Historical 2=Parameterized
DistributionType = Literal[1, 2]  # 1=Normal 2=Fat-tailed
CashflowType = Literal[0, 1, 2, 3, 4, 5, 6, 8, 9]
CashflowFrequency = Literal["monthly", "quarterly", "annual"]
LifeExpectancyModel = Literal["single", "uniform"]


# ── Sub-schemas ──────────────────────────────────────────────────────────────

class AssetAllocation(BaseModel):
    """A single line in a portfolio."""
    model_config = ConfigDict(extra="forbid")

    asset: str = Field(..., description="Asset alias, e.g. NIFTY_50, SBI_GILT, GOLD.")
    weight: float = Field(..., ge=0.0, le=1.0, description="Portfolio weight in [0, 1]. All weights must sum to 1.0.")


class AssetSummary(BaseModel):
    """Asset metadata as returned in the simulation response."""
    model_config = ConfigDict(extra="forbid")

    alias: str
    name: str
    weight: float


class PercentileBand(BaseModel):
    """The 5 default percentile levels used across output tables."""
    model_config = ConfigDict(extra="forbid")

    p10: float
    p25: float
    p50: float
    p75: float
    p90: float


class AssetInfoResponse(BaseModel):
    """Details for a single asset alias."""
    model_config = ConfigDict(extra="forbid")

    alias: str
    name: str
    category: str
    data_code: str
    default_mean: Optional[float] = None
    default_std: Optional[float] = None


class AssetListItem(BaseModel):
    """Compact asset entry for listings and search."""
    model_config = ConfigDict(extra="forbid")

    alias: str
    name: str
    category: str


class TerminalDistribution(BaseModel):
    """Real histogram of final portfolio balances across simulation paths."""
    model_config = ConfigDict(extra="forbid")

    bin_edges: List[float]
    bin_counts: List[int]


# ── Main request ─────────────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    """
    Full Monte Carlo simulation request.

    Accepts every parameter the previous frontend supported, plus a couple of
    convenience fields. Optional fields fall back to sensible Indian-market
    defaults (60/40 Nifty 50 / SBI Gilt, 30-year horizon, 1000 sims).
    """
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "initial_balance": 1000000,
                    "years": 30,
                    "simulations": 1000,
                    "assets": [
                        {"asset": "NIFTY_50", "weight": 0.60},
                        {"asset": "NIFTY_MIDCAP_150", "weight": 0.40},
                    ],
                    "model": 1,
                    "bootstrap_model": 1,
                    "rebalance_frequency": 1,
                    "inflation_adjusted": True,
                    "seed": 42,
                }
            ]
        },
    )

    # ── Core ────────────────────────────────────────────────────────────────
    initial_balance: float = Field(1_000_000, gt=0, description="Starting portfolio value in INR.")
    years: int = Field(30, ge=1, le=100, description="Simulation horizon in years.")
    simulations: int = Field(1000, ge=10, le=10000, description="Number of Monte Carlo paths.")
    assets: List[AssetAllocation] = Field(
        default_factory=lambda: [
            AssetAllocation(asset="NIFTY_50", weight=0.60),
            AssetAllocation(asset="NIFTY_MIDCAP_150", weight=0.40),
        ],
        description="Portfolio composition. Weights must sum to 1.0.",
    )

    # ── Simulation model ────────────────────────────────────────────────────
    model: Model = Field(1, description="1=Historical, 2=Statistical, 3=Parameterized, 4=Forecasted.")
    time_series_model: TimeSeriesModel = Field(1, description="For Model 4: 1=Normal, 3=GARCH.")
    distribution_type: DistributionType = Field(1, description="For Model 3: 1=Normal, 2=Fat-tailed t-dist.")
    degrees_of_freedom: int = Field(30, ge=5, le=50, description="d.o.f. for the Student-t (Model 3 fat-tailed).")

    # ── Historical bootstrap ────────────────────────────────────────────────
    bootstrap_model: BootstrapModel = Field(1, description="0=SingleMonth, 1=SingleYear, 2=Block bootstrap.")
    bootstrap_min_years: int = Field(1, ge=1, le=30, description="Min block length in years (Block bootstrap).")
    bootstrap_max_years: int = Field(20, ge=1, le=30, description="Max block length in years (Block bootstrap).")
    circular_bootstrap: bool = Field(True, description="Wrap-around at end of history if true.")

    # ── History window ──────────────────────────────────────────────────────
    use_full_history: bool = Field(True, description="Use full available history if true.")
    start_year: Optional[int] = Field(None, description="Restrict historical window (inclusive).")
    end_year: Optional[int] = Field(None, description="Restrict historical window (inclusive).")

    # ── Custom parameters (Models 2 & 3) ────────────────────────────────────
    historical_volatility: bool = Field(True, description="Use historical vol if true; else custom_stds.")
    historical_correlations: bool = Field(True, description="Use historical correlations if true; else identity or custom.")
    custom_means: Optional[List[float]] = Field(None, description="Annual mean return per asset (Models 2/3).")
    custom_stds: Optional[List[float]] = Field(None, description="Annual std dev per asset (Models 2/3).")
    custom_correlation: Optional[List[List[float]]] = Field(None, description="n×n correlation matrix (Model 3 only).")

    # ── Rebalancing ─────────────────────────────────────────────────────────
    rebalance_frequency: RebalanceFrequency = Field(1, description="0=None, 1=Annual, 2=Semi, 3=Quarterly, 4=Monthly.")

    # ── Inflation ───────────────────────────────────────────────────────────
    inflation_adjusted: bool = Field(True, description="Return results in real (inflation-adjusted) terms.")
    inflation_model: InflationModel = Field(1, description="1=Historical CPI bootstrap, 2=Parameterized.")
    inflation_mean: float = Field(0.04, ge=0, le=1, description="Annual mean inflation.")
    inflation_volatility: float = Field(0.03, ge=0, le=1, description="Annual inflation volatility (parametric).")

    # ── Stress ──────────────────────────────────────────────────────────────
    sequence_stress_test: int = Field(0, ge=0, le=10, description="Place N worst years first; 0=disabled.")

    # ── Cash flows ──────────────────────────────────────────────────────────
    cashflow_type: Optional[CashflowType] = Field(None, description="0=None, 1=Contribute, 2=Withdraw, 3=Fixed%, 4=LifeExp, 5=RollAvg, 6=Geom, 8=Fixed+pct, 9=Contrib+pct.")
    cashflow_amount: Optional[float] = Field(None, description="Cashflow amount per period (INR).")
    cashflow_frequency: Optional[CashflowFrequency] = Field(None, description="monthly, quarterly, or annual.")
    withdrawal_percentage: Optional[float] = Field(None, ge=0, le=100, description="For type 3: fixed % of balance per period.")
    pct_change: Optional[float] = Field(None, ge=0, description="Annual % step-up for types 8 and 9. E.g. 0.05 = 5% yearly increase in amount.")
    rolling_periods: Optional[int] = Field(None, ge=2, le=5, description="For type 5: rolling average window.")
    smoothing_rate: Optional[float] = Field(None, ge=0.5, le=0.9, description="For type 6: geometric smoothing rate.")
    life_expectancy_model: Optional[LifeExpectancyModel] = Field(None, description="For type 4: 'single' or 'uniform'.")
    current_age: Optional[int] = Field(None, ge=30, le=95, description="For type 4: current age.")

    # ── Rates & output ──────────────────────────────────────────────────────
    risk_free_rate: float = Field(0.0483, ge=0, le=1, description="Annualized risk-free rate for Sharpe/Sortino.")
    percentiles: List[float] = Field(
        default_factory=lambda: [0.10, 0.25, 0.50, 0.75, 0.90],
        description="Percentile levels for balance tables.",
    )
    return_intervals: List[float] = Field(
        default_factory=lambda: [0.00, 0.025, 0.05, 0.075, 0.10, 0.125],
        description="Not yet wired — accepted but the engine uses hardcoded thresholds.",
    )

    # ── Placeholders (not yet wired into the engine) ────────────────────────
    tax_enabled: bool = Field(False, description="Not yet implemented — raises 400 if true.")

    # ── Reproducibility ─────────────────────────────────────────────────────
    seed: int = Field(42, description="RNG seed. Same seed + same request = same output.")


# ── Response ─────────────────────────────────────────────────────────────────

class SimulateResponse(BaseModel):
    """Complete Monte Carlo output. All numeric values are raw floats (no formatting)."""
    model_config = ConfigDict(extra="forbid")

    # ── Run metadata ───────────────────────────────────────────────────
    n_simulations: int
    n_years: int
    assets: List[AssetSummary] = Field(..., description="Resolved portfolio with alias, display name, and weight.")
    config_echo: Dict = Field(..., description="Full request echoed back for auditability.")

    # ── Headline KPIs ──────────────────────────────────────────────────
    median_cagr: float = Field(..., description="Median time-weighted annualized return across sims (decimal).")
    success_rate: float = Field(..., description="Fraction of paths that ended above 1% of initial balance.")
    median_final_balance: float = Field(..., description="Median terminal portfolio value (INR).")
    swr: float = Field(..., description="Safe Withdrawal Rate — max rate with ≥95% survival.")
    pwr: float = Field(..., description="Perpetual Withdrawal Rate — max rate where median balance persists.")

    # ── Tables ─────────────────────────────────────────────────────────
    performance_summary: Dict[str, PercentileBand] = Field(
        ..., description="9 stats × 5 percentiles. Keys: time_weighted_return_nominal, ..., maximum_drawdown."
    )
    balance_percentiles: Dict[str, PercentileBand] = Field(
        ..., description="Year (string) → percentile balances. For plotting the fan chart."
    )
    expected_returns: Dict[str, Dict[str, Optional[float]]] = Field(
        ..., description="Return threshold (e.g. '>=5%') → horizon-year → probability. Cell is null if horizon exceeds simulated years."
    )
    loss_probabilities: Dict[str, Dict[str, Optional[float]]] = Field(
        ..., description="Loss magnitude threshold (e.g. '>= 10%' means 'loss of 10% or more') → horizon-year → probability. Cell is null if horizon exceeds simulated years."
    )
    simulated_assets: Dict[str, Dict[str, Optional[float]]] = Field(
        ..., description="Per-asset realized CAGR, expected_return, volatility, and pairwise correlations. Cell is null if unavailable."
    )

    # ── Distribution details ───────────────────────────────────────────
    terminal_distribution: TerminalDistribution = Field(
        ..., description="Real histogram of final balances — bin_edges (len N+1), bin_counts (len N)."
    )
    drawdown_percentiles: PercentileBand = Field(
        ..., description="Max-drawdown percentiles across paths (decimal, negative)."
    )


# ── Meta / discovery ─────────────────────────────────────────────────────────

class EndpointInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    method: str
    tag: str
    description: str


class RootResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service: str
    version: str
    docs: str
    openapi: str
    endpoints: List[EndpointInfo]


class ModelCapability(BaseModel):
    """What a given simulation model supports. Meant for LLM tool selection."""
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    description: str
    supports_bootstrap: bool
    supports_custom_mean_std: bool
    supports_custom_correlation: bool
    supports_fat_tails: bool
    supports_garch: bool
    recommended_when: str


class ModelsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models: List[ModelCapability]


class ExamplePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    request: Dict


class ExamplesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    examples: List[ExamplePayload]


class AssetListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total: int
    assets: List[AssetListItem]


class AssetSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    total: int
    results: List[AssetListItem]


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str
    detail: str

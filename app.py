"""
FastAPI web service for Macrowise Monte Carlo Simulator.
Deployed on Render at https://macrowise.onrender.com
"""
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import numpy as np
from pathlib import Path

from macrowise import MonteCarloConfig, MonteCarlo, CashFlowConfig, format_inr

app = FastAPI(
    title="Macrowise Monte Carlo Simulator",
    description=(
        "Monte Carlo portfolio simulation engine for Indian markets. "
        "PortfolioVisualizer-compatible with NSE TRI, gilt funds, and Indian tax rules."
    ),
    version="1.0.0",
)

_BASE = Path(__file__).parent


# ── Request / Response Models ────────────────────────────────────────────────

class AssetAllocation(BaseModel):
    asset: str = Field(..., description="Asset alias, e.g. NIFTY_50, SBI_GILT, GOLD")
    weight: float = Field(..., ge=0, le=1, description="Portfolio weight (0-1)")


class MonteCarloRequest(BaseModel):
    initial_balance: float = Field(1_000_000, description="Starting portfolio value (INR)")
    years: int = Field(30, ge=1, le=100, description="Simulation horizon in years")
    simulations: int = Field(1000, ge=10, le=10000, description="Number of Monte Carlo paths")
    assets: List[AssetAllocation] = Field(
        [AssetAllocation(asset="NIFTY_50", weight=0.60),
         AssetAllocation(asset="SBI_GILT", weight=0.40)],
        description="Portfolio asset allocations",
    )
    model: int = Field(1, ge=1, le=4, description="1=Historical, 2=Statistical, 3=Parameterized, 4=Forecasted")
    time_series_model: int = Field(1, ge=1, le=3, description="1=Normal, 3=GARCH")
    bootstrap_model: int = Field(1, ge=0, le=2, description="0=SingleMonth, 1=SingleYear, 2=Block")
    bootstrap_min_years: int = Field(1, ge=1, le=30, description="Minimum block length for bootstrap")
    bootstrap_max_years: int = Field(20, ge=1, le=30, description="Maximum block length for bootstrap")
    circular_bootstrap: bool = Field(True, description="Allow block bootstrapping to be circular")
    rebalance_frequency: int = Field(1, ge=0, le=4, description="0=None, 1=Annual, 2=Semi-Annual, 3=Quarterly, 4=Monthly")
    inflation_adjusted: bool = Field(True, description="Return results in real (inflation-adjusted) terms")
    inflation_model: int = Field(1, ge=1, le=2, description="1=Historical, 2=Parameterized")
    inflation_mean: float = Field(0.04, ge=0, le=1, description="Mean inflation rate")
    inflation_volatility: float = Field(0.03, ge=0, le=1, description="Inflation volatility")
    sequence_stress_test: int = Field(0, ge=0, le=10, description="0=None, 1-10=Worst N years first")

    # Statistical/Parameterized model settings
    historical_volatility: bool = Field(True, description="Use historical volatility or specify expected")
    historical_correlations: bool = Field(True, description="Use historical correlations or import custom")
    custom_means: Optional[List[float]] = Field(None, description="Custom mean returns for each asset")
    custom_stds: Optional[List[float]] = Field(None, description="Custom standard deviations for each asset")
    custom_correlation: Optional[List[List[float]]] = Field(None, description="Custom correlation matrix")
    risk_free_rate: float = Field(0.0483, ge=0, le=1, description="Risk-free rate for Sharpe ratio")
    distribution_type: int = Field(1, ge=1, le=2, description="1=Normal, 2=Fat-tailed")
    degrees_of_freedom: int = Field(30, ge=5, le=50, description="Degrees of freedom for t-distribution")

    # Time series settings
    use_full_history: bool = Field(True, description="Use full available history for asset returns")
    start_year: Optional[int] = Field(None, description="Start year for historical returns")
    end_year: Optional[int] = Field(None, description="End year for historical returns")

    # Cash flow inputs
    cashflow_type: Optional[int] = Field(None, description="0=None, 1=Contribute, 2=Withdraw, 3=Fixed%, 4=Life Exp, 5=Rolling Avg, 6=Geometric")
    cashflow_amount: Optional[float] = Field(None, description="Cashflow amount (INR per period)")
    cashflow_frequency: Optional[str] = Field(None, description="monthly, quarterly, annual")
    withdrawal_percentage: Optional[float] = Field(None, ge=0, le=100, description="Fixed withdrawal % per period")
    rolling_periods: Optional[int] = Field(None, ge=2, le=5, description="Rolling average periods")
    smoothing_rate: Optional[float] = Field(None, ge=0.5, le=0.9, description="Smoothing rate for geometric rule")
    life_expectancy_model: Optional[str] = Field(None, description="single or uniform")
    current_age: Optional[int] = Field(None, ge=30, le=95, description="Current age for life expectancy")

    # Output customization
    percentiles: List[float] = Field(default_factory=lambda: [0.10, 0.25, 0.50, 0.75, 0.90], description="Percentile intervals")
    return_intervals: List[float] = Field(default_factory=lambda: [0.00, 0.025, 0.05, 0.075, 0.10, 0.125], description="Return thresholds")

    # Tax and investment horizon (US only - currently placeholders)
    tax_enabled: bool = Field(False, description="Tax calculations (experimental)")
    investment_horizon: int = Field(1, ge=1, le=2, description="1=Simulated Period, 2=Perpetual")

    # Random seed
    seed: int = Field(42, description="Random seed for reproducibility")


class PercentileRow(BaseModel):
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float


class MonteCarloResponse(BaseModel):
    n_simulations: int
    n_years: int
    assets: List[str]
    median_cagr: float
    success_rate: float
    median_final_balance: float
    swr: float
    pwr: float
    performance_summary: dict
    balance_percentiles: dict
    loss_probabilities: dict
    expected_returns: Optional[dict] = None
    simulated_assets: Optional[dict] = None


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/api", summary="Service status")
def api_root():
    return {
        "service": "Macrowise Monte Carlo Simulator",
        "status": "running",
        "version": "1.0.0",
        "docs": "/docs",
        "ui": "/",
    }


@app.get("/", response_class=FileResponse, include_in_schema=False)
def homepage():
    """Serve the web UI."""
    return _BASE / "templates" / "index.html"


@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}


@app.get("/assets", summary="List available assets")
def list_assets():
    from macrowise.data.asset_registry import list_asset_aliases, get_asset
    aliases = list_asset_aliases()
    assets = []
    for alias in aliases:
        info = get_asset(alias)
        assets.append({
            "alias": alias,
            "name": info.name if info else alias,
            "category": info.category if info else "Unknown",
        })
    return {"total": len(assets), "assets": assets}


@app.get("/assets/{alias}", summary="Get asset info")
def get_asset_info(alias: str):
    from macrowise import get_asset, get_asset_data_code
    info = get_asset(alias)
    if info is None:
        raise HTTPException(404, f"Asset '{alias}' not found")
    return {
        "alias": alias,
        "name": info.name,
        "category": info.category,
        "data_code": get_asset_data_code(alias),
        "default_mean": info.default_mean,
        "default_std": info.default_std,
    }


# ── Monte Carlo ──────────────────────────────────────────────────────────────

@app.post("/simulate", response_model=MonteCarloResponse, summary="Run Monte Carlo simulation")
def simulate(req: MonteCarloRequest):
    """Run a Monte Carlo simulation and return full results."""
    try:
        # Build asset list
        assets = [(a.asset, a.weight) for a in req.assets]
        total_weight = sum(w for _, w in assets)
        if abs(total_weight - 1.0) > 0.001:
            raise HTTPException(
                400,
                f"Asset weights must sum to 1.0, got {total_weight:.4f}",
            )

        # Build cashflow config if specified
        cashflow = None
        if req.cashflow_type is not None and req.cashflow_type != 0:
            freq = req.cashflow_frequency or "annual"
            cashflow = CashFlowConfig(
                adjustment_type=req.cashflow_type,
                amount=req.cashflow_amount or 0.0,
                growth_rate=0.0,
                frequency=freq,
                inflation_adjusted=req.inflation_adjusted,
                inflation_mean=req.inflation_mean,
                withdrawal_percentage=req.withdrawal_percentage or 4.0,
                rolling_periods=req.rolling_periods or 3,
                smoothing_rate=req.smoothing_rate or 0.75,
                life_expectancy_model=req.life_expectancy_model or "single",
                current_age=req.current_age or 30,
            )

        config = MonteCarloConfig(
            initial_balance=req.initial_balance,
            years=req.years,
            simulations=req.simulations,
            assets=assets,
            model=req.model,
            time_series_model=req.time_series_model,
            distribution_type=req.distribution_type,
            degrees_of_freedom=req.degrees_of_freedom,
            bootstrap_model=req.bootstrap_model,
            bootstrap_min_years=req.bootstrap_min_years,
            bootstrap_max_years=req.bootstrap_max_years,
            circular_bootstrap=req.circular_bootstrap,
            use_full_history=req.use_full_history,
            start_year=req.start_year,
            end_year=req.end_year,
            custom_means=np.array(req.custom_means) if req.custom_means else None,
            custom_stds=np.array(req.custom_stds) if req.custom_stds else None,
            custom_correlation=np.array(req.custom_correlation) if req.custom_correlation else None,
            risk_free_rate=req.risk_free_rate,
            sequence_stress_test=req.sequence_stress_test,
            use_historical_volatility=req.historical_volatility,
            use_historical_correlations=req.historical_correlations,
            rebalance_frequency=req.rebalance_frequency,
            inflation_model=req.inflation_model,
            inflation_mean=req.inflation_mean,
            inflation_volatility=req.inflation_volatility,
            inflation_adjusted=req.inflation_adjusted,
            cashflow=cashflow,
            percentiles=req.percentiles,
            seed=req.seed,
        )
        sim = MonteCarlo(config)
        results = sim.run()

        # Convert DataFrames to plain dicts
        # performance_summary: index=stat_name, columns=p10/p25/p50/p75/p90
        #   → needs transpose to {stat_name: {p10: val, ...}}
        # balance_percentiles: index=year, columns=p10/p25/...
        #   → already {year: {p10: val, ...}}
        # loss_probabilities: index=threshold, columns=1/3/5/...
        #   → already {threshold: {1: val, 3: val, ...}}

        perf_df = results.performance_summary
        # Transpose so keys are stat names, not percentiles
        perf_out = {}
        for stat in perf_df.index:
            row = {}
            for pct in perf_df.columns:
                row[pct] = str(perf_df.loc[stat, pct])
            perf_out[stat] = row

        # balance_percentiles: index = year, columns = p10..p90
        bal_out = {}
        for year in results.balance_percentiles.index:
            row = {}
            for pct in results.balance_percentiles.columns:
                row[pct] = float(results.balance_percentiles.loc[year, pct])
            bal_out[str(year)] = row

        # loss_probabilities: index = threshold, columns = years
        loss_out = {}
        for thr in results.loss_probabilities.index:
            row = {}
            for yr in results.loss_probabilities.columns:
                row[yr] = str(results.loss_probabilities.loc[thr, yr])
            loss_out[thr] = row

        # expected_returns: index = percentile, columns = years
        expected_out = {}
        if results.expected_returns is not None:
            for pct in results.expected_returns.index:
                row = {}
                for yr in results.expected_returns.columns:
                    row[yr] = str(results.expected_returns.loc[pct, yr])
                expected_out[pct] = row

        # simulated_assets: index = asset name, columns = correlations + stats
        sim_assets_out = {}
        if results.simulated_assets is not None:
            for asset in results.simulated_assets.index:
                row = {}
                for col in results.simulated_assets.columns:
                    row[col] = str(results.simulated_assets.loc[asset, col])
                sim_assets_out[asset] = row

        return MonteCarloResponse(
            n_simulations=results.n_sims,
            n_years=results.n_years,
            assets=results.asset_names,
            median_cagr=results.median_cagr,
            success_rate=results.success_rate,
            median_final_balance=results.median_final_balance,
            swr=results.swr,
            pwr=results.pwr,
            performance_summary=perf_out,
            balance_percentiles=bal_out,
            loss_probabilities=loss_out,
            expected_returns=expected_out,
            simulated_assets=sim_assets_out,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=str(e))

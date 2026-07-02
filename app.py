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


@app.get("/", response_class=FileResponse, include_in_schema=False)
def homepage():
    """Serve the web UI."""
    return _BASE / "templates" / "index.html"


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
    bootstrap_model: int = Field(1, ge=0, le=2, description="0=SingleMonth, 1=SingleYear, 2=Block")
    inflation_adjusted: bool = Field(True, description="Return results in real (inflation-adjusted) terms")
    cashflow_type: Optional[int] = Field(None, description="0=None, 1=Contribute, 2=Withdraw, 3=Fixed% withdrawal")
    cashflow_amount: Optional[float] = Field(None, description="Cashflow amount (INR per period)")
    cashflow_frequency: Optional[str] = Field("annual", description="monthly, quarterly, annual")
    withdrawal_percentage: Optional[float] = Field(None, ge=0, le=100, description="Fixed withdrawal % per period")
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
            if req.cashflow_type == 3 and req.withdrawal_percentage is not None:
                cashflow = CashFlowConfig(
                    adjustment_type=3,
                    withdrawal_percentage=req.withdrawal_percentage / 100.0,
                )
            elif req.cashflow_amount is not None:
                cashflow = CashFlowConfig(
                    adjustment_type=req.cashflow_type,
                    amount=req.cashflow_amount,
                    frequency=freq,
                )

        config = MonteCarloConfig(
            initial_balance=req.initial_balance,
            years=req.years,
            simulations=req.simulations,
            assets=assets,
            model=req.model,
            bootstrap_model=req.bootstrap_model,
            seed=req.seed,
            inflation_adjusted=req.inflation_adjusted,
            cashflow=cashflow,
        )
        sim = MonteCarlo(config)
        results = sim.run()

        return MonteCarloResponse(
            n_simulations=results.n_sims,
            n_years=results.n_years,
            assets=results.asset_names,
            median_cagr=results.median_cagr,
            success_rate=results.success_rate,
            median_final_balance=results.median_final_balance,
            swr=results.swr,
            pwr=results.pwr,
            performance_summary=results.performance_summary.to_dict(),
            balance_percentiles=results.balance_percentiles.to_dict(),
            loss_probabilities=results.loss_probabilities.to_dict(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=str(e))

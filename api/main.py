"""
Macrowise Monte Carlo Simulator — FastAPI service.

Designed for headless integration (main website, AI bot tool-use). No auth —
deploy behind Macrowise's gateway. Discoverability endpoints (GET /, /models,
/examples, /assets/search) let an LLM introspect and drive the API without
extra prompting.

Endpoints:
  GET  /                    Self-describing endpoint index
  GET  /health              Liveness probe
  GET  /models              Simulation model capability matrix
  GET  /examples            Sample request payloads
  GET  /assets              List all supported assets
  GET  /assets/search       Fuzzy search over asset aliases and names
  GET  /assets/{alias}      Detail for one asset
  POST /simulate            Run a Monte Carlo simulation
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.exceptions import HTTPException as StarletteHTTPException

from macrowise import MonteCarloConfig, MonteCarlo, CashFlowConfig
from macrowise.data.asset_registry import (
    get_asset,
    list_asset_aliases,
    get_asset_data_code,
)

from api.schemas import (
    SimulateRequest,
    SimulateResponse,
    AssetSummary,
    PercentileBand,
    TerminalDistribution,
    AssetInfoResponse,
    AssetListItem,
    AssetListResponse,
    AssetSearchResponse,
    RootResponse,
    EndpointInfo,
    ModelsResponse,
    ModelCapability,
    ExamplesResponse,
    ExamplePayload,
    ErrorResponse,
)


# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Macrowise Monte Carlo Simulator",
    version="2.0.0",
    description=(
        "Monte Carlo portfolio simulation engine for Indian markets.\n\n"
        "Supports 4 simulation models (Historical, Statistical, Parameterized, "
        "Forecasted GARCH), 3 bootstrap methods, inflation adjustment, rebalancing, "
        "cashflows (SIP/SWP/step-up), sequence-of-returns stress tests, and "
        "SWR/PWR analysis. Data covers 719 NSE/BSE indices and Nifty 500 stocks.\n\n"
        "**No auth** — deploy behind an API gateway."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    responses={
        400: {"model": ErrorResponse, "description": "Bad request"},
        500: {"model": ErrorResponse, "description": "Simulation engine error"},
    },
)

# CORS — open by default so the AI bot / website can call directly.
# Lock down `allow_origins` when a gateway is not in front.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ── Error handlers — always return machine-readable JSON ─────────────────────

@app.exception_handler(ValueError)
async def _value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": "bad_request", "detail": str(exc)})


@app.exception_handler(RuntimeError)
async def _runtime_error_handler(request: Request, exc: RuntimeError):
    return JSONResponse(status_code=500, content={"error": "engine_error", "detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "detail": exc.errors()},
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Coerce every HTTPException into the {error, detail} shape."""
    error_slug = {400: "bad_request", 404: "not_found", 405: "method_not_allowed"}.get(
        exc.status_code, "http_error"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_slug, "detail": str(exc.detail)},
    )


# ── Meta / discoverability ───────────────────────────────────────────────────

@app.get("/", response_model=RootResponse, tags=["meta"], summary="Self-describing API index")
def root():
    """
    Returns the list of available endpoints with descriptions.

    Designed to be the first call an LLM tool makes — one round-trip to learn
    the full surface.
    """
    endpoints = [
        EndpointInfo(path="/", method="GET", tag="meta", description="This endpoint — API self-description."),
        EndpointInfo(path="/health", method="GET", tag="meta", description="Liveness probe."),
        EndpointInfo(path="/models", method="GET", tag="catalog", description="Available simulation models with capability flags."),
        EndpointInfo(path="/examples", method="GET", tag="catalog", description="Sample request payloads for /simulate."),
        EndpointInfo(path="/assets", method="GET", tag="catalog", description="List of all 719 supported assets (indices + stocks)."),
        EndpointInfo(path="/assets/search", method="GET", tag="catalog", description="Fuzzy search over asset aliases and names."),
        EndpointInfo(path="/assets/{alias}", method="GET", tag="catalog", description="Detail for a single asset alias."),
        EndpointInfo(path="/simulate", method="POST", tag="simulate", description="Run a Monte Carlo simulation. Body: SimulateRequest."),
    ]
    return RootResponse(
        service="Macrowise Monte Carlo Simulator",
        version=app.version,
        docs="/docs",
        openapi="/openapi.json",
        endpoints=endpoints,
    )


@app.get("/health", tags=["meta"], summary="Liveness probe")
def health():
    return {"status": "ok"}


@app.get("/models", response_model=ModelsResponse, tags=["catalog"], summary="Simulation model capability matrix")
def models():
    """
    Returns the 4 simulation models with boolean capability flags. An LLM tool
    can inspect this to pick the right `model` value for the user's intent.
    """
    return ModelsResponse(
        models=[
            ModelCapability(
                id=1,
                name="Historical Bootstrap",
                description="Resample from actual monthly returns. No distributional assumption; preserves fat tails and correlations naturally.",
                supports_bootstrap=True,
                supports_custom_mean_std=False,
                supports_custom_correlation=False,
                supports_fat_tails=False,
                supports_garch=False,
                recommended_when="Default choice. Use when you trust the historical record as representative.",
            ),
            ModelCapability(
                id=2,
                name="Statistical",
                description="Historical bootstrap with returns rescaled to custom mean/std targets.",
                supports_bootstrap=True,
                supports_custom_mean_std=True,
                supports_custom_correlation=False,
                supports_fat_tails=False,
                supports_garch=False,
                recommended_when="You want historical shape but a different long-run mean or volatility.",
            ),
            ModelCapability(
                id=3,
                name="Parameterized",
                description="Synthetic returns from Normal or Student-t distribution with a specified correlation matrix.",
                supports_bootstrap=False,
                supports_custom_mean_std=True,
                supports_custom_correlation=True,
                supports_fat_tails=True,
                supports_garch=False,
                recommended_when="You need a specific parametric distribution or custom correlations.",
            ),
            ModelCapability(
                id=4,
                name="Forecasted (GARCH)",
                description="Time-varying volatility via GARCH(1,1) with cross-asset Cholesky correlation.",
                supports_bootstrap=False,
                supports_custom_mean_std=True,
                supports_custom_correlation=True,
                supports_fat_tails=False,
                supports_garch=True,
                recommended_when="You need volatility clustering and time-varying risk.",
            ),
        ]
    )


@app.get("/examples", response_model=ExamplesResponse, tags=["catalog"], summary="Sample /simulate request bodies")
def examples():
    """Curated example payloads — copy, tweak, POST to /simulate."""
    return ExamplesResponse(
        examples=[
            ExamplePayload(
                name="default_large_mid",
                description="30-year 60/40 Nifty 50 / Nifty Midcap 150, historical bootstrap, annual rebalance.",
                request={
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
                },
            ),
            ExamplePayload(
                name="sip_25_years",
                description="Monthly SIP of ₹25,000 into Nifty 500, 25-year horizon, block bootstrap.",
                request={
                    "initial_balance": 100000,
                    "years": 25,
                    "simulations": 2000,
                    "assets": [{"asset": "NIFTY_500", "weight": 1.0}],
                    "model": 1,
                    "bootstrap_model": 2,
                    "bootstrap_min_years": 3,
                    "bootstrap_max_years": 10,
                    "cashflow_type": 1,
                    "cashflow_amount": 25000,
                    "cashflow_frequency": "monthly",
                    "inflation_adjusted": True,
                    "seed": 7,
                },
            ),
            ExamplePayload(
                name="retirement_swp",
                description="₹40k monthly withdrawal from a ₹2Cr corpus, 30-year retirement.",
                request={
                    "initial_balance": 20000000,
                    "years": 30,
                    "simulations": 2000,
                    "assets": [
                        {"asset": "NIFTY_50", "weight": 0.60},
                        {"asset": "NIFTY_MIDCAP_150", "weight": 0.25},
                        {"asset": "NIFTY_SMALLCAP_250", "weight": 0.15},
                    ],
                    "model": 1,
                    "bootstrap_model": 1,
                    "cashflow_type": 2,
                    "cashflow_amount": 40000,
                    "cashflow_frequency": "monthly",
                    "rebalance_frequency": 1,
                    "inflation_adjusted": True,
                    "seed": 42,
                },
            ),
            ExamplePayload(
                name="fat_tail_parametric",
                description="Model 3 with Student-t returns (df=10) — heavier tails than Normal.",
                request={
                    "initial_balance": 1000000,
                    "years": 20,
                    "simulations": 3000,
                    "assets": [
                        {"asset": "NIFTY_500", "weight": 0.70},
                        {"asset": "NIFTY_50", "weight": 0.30},
                    ],
                    "model": 3,
                    "distribution_type": 2,
                    "degrees_of_freedom": 10,
                    "historical_volatility": True,
                    "historical_correlations": True,
                    "rebalance_frequency": 1,
                    "seed": 42,
                },
            ),
        ]
    )


# ── Assets catalog ───────────────────────────────────────────────────────────

@app.get("/assets", response_model=AssetListResponse, tags=["catalog"], summary="List all supported assets")
def list_assets():
    aliases = list_asset_aliases()
    items: list[AssetListItem] = []
    for alias in aliases:
        info = get_asset(alias)
        items.append(AssetListItem(
            alias=alias,
            name=info.name if info else alias,
            category=info.category if info else "unknown",
        ))
    return AssetListResponse(total=len(items), assets=items)


@app.get("/assets/search", response_model=AssetSearchResponse, tags=["catalog"], summary="Fuzzy-search assets")
def search_assets(
    q: str = Query(..., min_length=1, description="Search term. Matches alias, name, and category (case-insensitive substring)."),
    limit: int = Query(50, ge=1, le=500, description="Max results to return."),
    category: Optional[str] = Query(None, description="Optional category filter (exact match)."),
):
    """
    Substring match across alias, display name, and category. Useful for the
    AI bot to resolve fuzzy asset names like 'nifty large cap' → NIFTY_100.
    """
    needle = q.lower().strip()
    results: list[AssetListItem] = []
    for alias in list_asset_aliases():
        info = get_asset(alias)
        name = info.name if info else alias
        cat = info.category if info else "unknown"
        if category and cat != category:
            continue
        hay = f"{alias} {name} {cat}".lower()
        if needle in hay:
            results.append(AssetListItem(alias=alias, name=name, category=cat))
        if len(results) >= limit:
            break
    return AssetSearchResponse(query=q, total=len(results), results=results)


@app.get("/assets/{alias}", response_model=AssetInfoResponse, tags=["catalog"], summary="Get detail for one asset")
def asset_detail(alias: str):
    info = get_asset(alias)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Asset '{alias}' not found")
    return AssetInfoResponse(
        alias=alias,
        name=info.name,
        category=info.category,
        data_code=get_asset_data_code(alias),
        default_mean=info.default_mean,
        default_std=info.default_std,
    )


# ── /simulate ────────────────────────────────────────────────────────────────

def _percentile_band(arr: np.ndarray) -> PercentileBand:
    p = np.percentile(arr, [10, 25, 50, 75, 90])
    return PercentileBand(p10=float(p[0]), p25=float(p[1]), p50=float(p[2]), p75=float(p[3]), p90=float(p[4]))


def _perf_row_to_band(df, row_key: str) -> PercentileBand:
    """Convert a row of the performance_summary DataFrame to a PercentileBand of floats.

    The engine returns some cells as pre-formatted strings (e.g. '11.23%'). We
    strip suffixes and parse back to raw floats.
    """
    def _to_float(v):
        if isinstance(v, (int, float, np.integer, np.floating)):
            return float(v)
        s = str(v).strip().replace(",", "")
        if s.endswith("%"):
            return float(s[:-1]) / 100.0
        # Strip INR / currency-ish glyphs
        for ch in ("₹", "$"):
            s = s.replace(ch, "")
        try:
            return float(s)
        except ValueError:
            return float("nan")

    row = df.loc[row_key]
    return PercentileBand(
        p10=_to_float(row["p10"]),
        p25=_to_float(row["p25"]),
        p50=_to_float(row["p50"]),
        p75=_to_float(row["p75"]),
        p90=_to_float(row["p90"]),
    )


# Map engine index row-labels → snake_case keys we expose in the API.
_PERF_KEY_MAP = {
    "Time Weighted Rate of Return (nominal)": "time_weighted_return_nominal",
    "Time Weighted Rate of Return (real)": "time_weighted_return_real",
    "Portfolio End Balance (nominal)": "portfolio_end_balance_nominal",
    "Portfolio End Balance (real)": "portfolio_end_balance_real",
    "Annual Mean Return": "annual_mean_return",
    "Annualized Volatility": "annualized_volatility",
    "Sharpe Ratio": "sharpe_ratio",
    "Sortino Ratio": "sortino_ratio",
    "Maximum Drawdown": "maximum_drawdown",
}


def _parse_percentage_cell(v) -> Optional[float]:
    """Engine tables occasionally emit '12.34%' strings or '—' for N/A. Return None for N/A."""
    if v is None:
        return None
    if isinstance(v, (int, float, np.integer, np.floating)):
        f = float(v)
        return None if math.isnan(f) else f
    s = str(v).strip()
    if s in ("—", "-", "nan", "NaN", "None", ""):
        return None
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100.0
        except ValueError:
            return None
    try:
        f = float(s)
        return None if math.isnan(f) else f
    except ValueError:
        return None


@app.post(
    "/simulate",
    response_model=SimulateResponse,
    tags=["simulate"],
    summary="Run a Monte Carlo simulation",
)
def simulate(req: SimulateRequest):
    """
    Run a full Monte Carlo simulation and return all output tables.

    All numeric fields in the response are raw floats (no formatting).
    """
    if req.tax_enabled:
        raise HTTPException(400, "tax_enabled is not yet implemented.")

    # ── Validate portfolio weights ──────────────────────────────────────────
    assets = [(a.asset, a.weight) for a in req.assets]
    total_weight = sum(w for _, w in assets)
    if abs(total_weight - 1.0) > 0.001:
        raise HTTPException(400, f"Asset weights must sum to 1.0, got {total_weight:.4f}")

    # ── Build cashflow config if requested ──────────────────────────────────
    cashflow = None
    if req.cashflow_type is not None and req.cashflow_type != 0:
        cashflow = CashFlowConfig(
            adjustment_type=req.cashflow_type,
            amount=req.cashflow_amount or 0.0,
            growth_rate=0.0,
            frequency=req.cashflow_frequency or "annual",
            inflation_adjusted=req.inflation_adjusted,
            inflation_mean=req.inflation_mean,
            withdrawal_percentage=req.withdrawal_percentage or 4.0,
            pct_change=req.pct_change or 0.0,
            rolling_periods=req.rolling_periods or 3,
            smoothing_rate=req.smoothing_rate or 0.75,
            life_expectancy_model=req.life_expectancy_model or "single",
            current_age=req.current_age or 30,
        )

    # ── Build engine config ─────────────────────────────────────────────────
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

    # ── Resolve asset summaries ─────────────────────────────────────────────
    asset_summaries: list[AssetSummary] = []
    for (alias, weight), name in zip(assets, results.asset_names):
        asset_summaries.append(AssetSummary(alias=alias, name=name, weight=weight))

    # ── performance_summary → typed dict of PercentileBand ──────────────────
    perf_df = results.performance_summary
    perf_out: dict[str, PercentileBand] = {}
    for engine_key, api_key in _PERF_KEY_MAP.items():
        if engine_key in perf_df.index:
            perf_out[api_key] = _perf_row_to_band(perf_df, engine_key)

    # ── balance_percentiles → year (str) → PercentileBand ───────────────────
    bal_out: dict[str, PercentileBand] = {}
    bal_df = results.balance_percentiles
    for year in bal_df.index:
        bal_out[str(year)] = PercentileBand(
            p10=float(bal_df.loc[year, "p10"]),
            p25=float(bal_df.loc[year, "p25"]),
            p50=float(bal_df.loc[year, "p50"]),
            p75=float(bal_df.loc[year, "p75"]),
            p90=float(bal_df.loc[year, "p90"]),
        )

    # ── expected_returns → threshold → horizon → probability ────────────────
    exp_out: dict[str, dict[str, float]] = {}
    if results.expected_returns is not None:
        er = results.expected_returns
        for thr in er.index:
            exp_out[str(thr)] = {str(h): _parse_percentage_cell(er.loc[thr, h]) for h in er.columns}

    # ── loss_probabilities → threshold → horizon → probability ──────────────
    loss_out: dict[str, dict[str, float]] = {}
    lp = results.loss_probabilities
    for thr in lp.index:
        loss_out[str(thr)] = {str(h): _parse_percentage_cell(lp.loc[thr, h]) for h in lp.columns}

    # ── simulated_assets → asset → {corrs..., cagr, expected_return, volatility} ──
    sim_assets_out: dict[str, dict[str, float]] = {}
    if results.simulated_assets is not None:
        sa = results.simulated_assets
        for asset in sa.index:
            row_out: dict[str, float] = {}
            for col in sa.columns:
                cell = sa.loc[asset, col]
                key = str(col).lower().replace(" ", "_")
                row_out[key] = _parse_percentage_cell(cell)
            sim_assets_out[str(asset)] = row_out

    # ── terminal_distribution: real histogram of final balances ─────────────
    final_balances = np.asarray(results.balance_paths[:, -1], dtype=float)
    counts, edges = np.histogram(final_balances, bins=50)
    terminal = TerminalDistribution(
        bin_edges=[float(e) for e in edges.tolist()],
        bin_counts=[int(c) for c in counts.tolist()],
    )

    # ── drawdown_percentiles: max drawdown per path ─────────────────────────
    bp = np.asarray(results.balance_paths, dtype=float)  # (n_sims, n_months+1)
    running_max = np.maximum.accumulate(bp, axis=1)
    # Guard against zero running max on wiped-out paths
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdowns = np.where(running_max > 0, bp / running_max - 1.0, -1.0)
    max_dd_per_path = drawdowns.min(axis=1)
    drawdown_band = _percentile_band(max_dd_per_path)

    return SimulateResponse(
        n_simulations=int(results.n_sims),
        n_years=int(results.n_years),
        assets=asset_summaries,
        config_echo=req.model_dump(),
        median_cagr=float(results.median_cagr),
        success_rate=float(results.success_rate),
        median_final_balance=float(results.median_final_balance),
        swr=float(results.swr),
        pwr=float(results.pwr),
        performance_summary=perf_out,
        balance_percentiles=bal_out,
        expected_returns=exp_out,
        loss_probabilities=loss_out,
        simulated_assets=sim_assets_out,
        terminal_distribution=terminal,
        drawdown_percentiles=drawdown_band,
    )

# Macrowise Monte Carlo Simulator

A Monte Carlo portfolio simulation engine for Indian markets, packaged as a
headless FastAPI service designed to plug into a website or an AI-bot tool.

- **Universe**: 719 Indian assets — 219 NSE / BSE indices (sector, size, style,
  factor, thematic) plus 500 Nifty 500 constituent stocks.
- **Models**: 4 simulation engines — Historical Bootstrap, Statistical
  (bootstrap + rescale), Parameterized (Normal or Student-t with custom
  correlation), Forecasted (GARCH(1,1) with cross-asset correlation).
- **Cash flows**: SIP contributions, SWP withdrawals, fixed-percentage rules,
  IRS-style life-expectancy schedules, and step-up variants.
- **Analytics**: nine performance percentiles, real histogram of terminal
  wealth, drawdown quantiles, expected-return and loss-probability tables,
  safe/perpetual withdrawal rates.
- **Delivery**: FastAPI REST layer + standalone Python library.

Everything the previous single-page demo UI exposed is available via the API.
This service is intended to sit behind the main Macrowise gateway and be
consumed by the production website and the AI bot.

---

## Table of Contents

1. [What Problem This Solves](#1-what-problem-this-solves)
2. [Repository Layout](#2-repository-layout)
3. [Setup](#3-setup)
4. [Running the Service](#4-running-the-service)
5. [The Request Schema](#5-the-request-schema)
6. [The Response Schema](#6-the-response-schema)
7. [12 Worked Examples With Real Results](#7-12-worked-examples-with-real-results)
8. [Simulation Models — Every Model in Detail](#8-simulation-models--every-model-in-detail)
9. [Cash Flow Types](#9-cash-flow-types)
10. [Historical Data](#10-historical-data)
11. [Test Coverage](#11-test-coverage)
12. [Frontend Integration Notes](#12-frontend-integration-notes)
13. [Known Limitations](#13-known-limitations)
14. [Architecture Notes](#14-architecture-notes)
15. [Reference Cards](#15-reference-cards)

---

## 1. What Problem This Solves

A user (or an AI bot on behalf of a user) walks in with a portfolio question
expressed in one or more of these forms:

- *"If I invest ₹10 lakh in 60/40 Nifty 50 / Midcap for 30 years, what's the range of outcomes?"*
- *"Can I retire on ₹2 crore drawing ₹40k a month?"*
- *"What's the probability my SIP hits ₹1 crore in 15 years?"*
- *"How much worse would things look if the market crashes right at the start of my retirement?"*
- *"Compare a factor-tilted portfolio (Alpha + Momentum + Quality + Low-Vol) against 100% Nifty 500."*
- *"Model a concentrated 3-stock bet with fat-tailed returns."*
- Any combination of the above.

The service exposes a single `POST /simulate` endpoint that runs the requested
Monte Carlo simulation and returns:

- **Headline KPIs**: median CAGR, success rate, median terminal balance, Safe
  Withdrawal Rate, Perpetual Withdrawal Rate.
- **Performance summary**: 9 statistics × 5 percentiles (returns, volatility,
  Sharpe, Sortino, drawdown, both nominal and inflation-adjusted).
- **Distribution details**: real histogram of terminal wealth (not a fitted
  bell curve), max-drawdown quantiles, year-by-year balance percentiles.
- **Probability tables**: probability of hitting a given annualised return, at
  each horizon; probability of a given loss size, at each horizon.
- **Per-asset diagnostics**: realised CAGR, expected return, volatility, and
  the pairwise correlation matrix.
- **Config echo**: the exact request that produced the numbers.

The engine is deterministic — same request + same `seed` returns identical
output.

---

## 2. Repository Layout

```
D:/Macrowise Monte Carlo Simulator/
├── api/                        FastAPI service
│   ├── __init__.py
│   ├── main.py                   endpoints, exception handlers, CORS
│   └── schemas.py                Pydantic request/response models
├── macrowise/                  Simulation library (usable standalone)
│   ├── engine/                   MC orchestrator, samplers, cashflow, stats
│   │   ├── monte_carlo.py          MonteCarloConfig, MonteCarloSimulation, MonteCarloResults
│   │   ├── bootstrap.py            BootstrapSampler (single-month, single-year, block)
│   │   ├── parametric.py           NormalSampler, FatTailedSampler, GARCHSampler
│   │   ├── cashflow.py             CashFlowConfig, CashFlowEngine
│   │   ├── stats.py                Sharpe, Sortino, SWR, PWR, percentiles
│   │   ├── tax.py                  Indian tax calculator (not yet wired in)
│   │   └── glide_path.py           Career→retirement allocation glide (not yet exposed)
│   ├── data/                     pickle loader + 719-asset registry
│   │   ├── loader.py               lazy-cached DataFrame accessors
│   │   ├── asset_registry.py       alias → data_code + metadata
│   │   └── _generated_index_mapping.py   auto-generated alias table
│   └── viz/                      matplotlib chart helpers (optional)
├── data/                       Configuration + processed pickles
│   ├── processed/                binary market data (see Section 10)
│   ├── tax_rules_india.json      FY 2024-25 tax reference
│   └── life_expectancy_metadata.json
├── tests/
│   └── test_api_exhaustive.py    153-case integration test suite
├── Dockerfile                  production image (python:3.11-slim)
├── docker-compose.yml          local orchestration with healthcheck
├── .dockerignore
├── render.yaml                 Render.com blueprint
├── requirements.txt
├── run_api.sh                  ./run_api.sh dev | prod
└── README.md                   (this file)
```

---

## 3. Setup

### 3.1 Prerequisites

- Python 3.10 or newer
- `pip`
- `git`

### 3.2 Clone

```bash
git clone https://github.com/deltaparticle/macrowise-monte-carlo.git
cd macrowise-monte-carlo
```

### 3.3 Virtual environment (recommended)

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Windows (Git Bash)
python -m venv .venv
source .venv/Scripts/activate
```

### 3.4 Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` pins:

```
numpy>=1.24.0
pandas>=2.0.0
matplotlib>=3.5.0
fastapi>=0.100.0
uvicorn>=0.23.0
python-multipart>=0.0.6
pydantic>=2.0.0
scipy>=1.10.0
```

### 3.5 Verify

```bash
python -c "from api.main import app; print('OK')"
python -c "from macrowise import MonteCarloConfig, MonteCarlo; print('OK')"
```

### 3.6 Data files

The `data/processed/` directory contains the pickle files (~15 MB) with historical
market data. These are committed to the repository. If you see a `FileNotFoundError`
on `/simulate`, verify that `data/processed/` contains these files:

- `all_monthly_returns_final.pkl`
- `all_annual_returns_final.pkl`
- `all_asset_statistics_final.pkl`
- `all_correlation_matrix_final.pkl`
- `all_covariance_matrix_final.pkl`
- `all_prices_final.pkl`
- `inflation_data.pkl`
- `dynamic_risk_free_rate.pkl`
- `life_expectancy_india.pkl`

---

## 4. Running the Service

### 4.1 Local (uvicorn)

```bash
# Dev — single worker, auto-reload
./run_api.sh dev
# or explicitly (macOS / Linux / Git Bash):
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Dev — Windows PowerShell / cmd.exe:
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Prod — two workers, no reload
./run_api.sh prod
# or explicitly (macOS / Linux / Git Bash):
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2 --timeout-keep-alive 300
```

Then visit:

- Swagger UI (interactive): http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

### 4.2 Docker

```bash
# Build and run directly
docker build -t macrowise-mc .
docker run -p 8000:8000 macrowise-mc

# Or with compose (includes healthcheck)
docker compose up -d
docker compose logs -f api
```

The image is `python:3.11-slim` + build tools for scipy/numpy wheels (~600 MB).
Healthcheck hits `/health` every 30 s; container is marked unhealthy after 3
consecutive failures.

The processed pickles under `data/processed/` **are baked into the image** by
default (they are 15 MB total). If you prefer to bind-mount instead, add
`data/processed` to `.dockerignore` and mount at runtime:

```bash
docker run -p 8000:8000 -v "$(pwd)/data:/app/data" macrowise-mc
```

### 4.3 Render

The repo ships a `render.yaml` blueprint. Any push to the tracked branch
auto-redeploys. The start command runs `uvicorn` with `--workers 2` and
`--timeout-keep-alive 300` for CPU-bound simulation work — no dashboard changes
needed.

### 4.4 Cold-start latency

All market data (~15 MB of pickle files) is lazily loaded into memory on the
**first** `/simulate` call after the process starts. The first request after a
deploy, container restart, or cold start will be noticeably slower (typically 5–15
seconds depending on the instance). Subsequent requests are fast because the data
is cached in-process. The Docker healthcheck has a 15-second `start_period` to
accommodate this. If your frontend or load balancer has a short timeout, increase
it or send a warm-up request after deploy.

### 4.5 Endpoint reference

| Method | Path | Description |
|---|---|---|
| `GET`  | `/`                    | Self-describing endpoint index. First call an LLM tool should make. |
| `GET`  | `/health`              | Liveness probe. Returns `{"status": "ok"}`. |
| `GET`  | `/models`              | Capability matrix for the 4 simulation models. |
| `GET`  | `/examples`            | Curated sample request payloads (also rendered in Swagger). |
| `GET`  | `/assets`              | List of all 719 assets with alias/name/category. |
| `GET`  | `/assets/search?q=`    | Fuzzy substring search across alias, name, category. Optional `limit`, `category` filters. |
| `GET`  | `/assets/{alias}`      | Detail for a single asset. |
| `POST` | `/simulate`            | Run a full Monte Carlo simulation. See Sections 5–6. |
| `GET`  | `/docs`                | Swagger UI. |
| `GET`  | `/redoc`               | ReDoc UI. |
| `GET`  | `/openapi.json`        | Machine-readable OpenAPI 3.1 schema. |

### 4.5 HTTP status codes

| Code | Meaning |
|---|---|
| 200  | Success. |
| 400  | Engine rejected the request semantically — e.g. weights don't sum to 1.0, unknown asset, `tax_enabled=true` (not yet implemented). Body: `{"error": "bad_request", "detail": "..."}`. |
| 404  | Resource not found — e.g. `GET /assets/UNKNOWN`. Body: `{"error": "not_found", "detail": "..."}`. |
| 422  | Schema validation error before the engine runs — unknown field, wrong type, out-of-range value. Body: `{"error": "validation_error", "detail": [Pydantic error records]}`. |
| 500  | Engine internal error — solver crash, unimplemented cashflow type. Body: `{"error": "engine_error", "detail": "..."}`. |

Every error response uses the same `{error, detail}` shape. The frontend can
surface the `detail` string directly to the user for 400/404, and format the
Pydantic error records for 422.

### 4.6 CORS

CORS is currently open (`allow_origins=["*"]`) so the AI bot and the website
can call the API from any origin without config. Before going to production
without a gateway in front, replace `"*"` with your actual frontend domain in
`api/main.py`:

```python
allow_origins=["https://app.macrowise.ai"],
```

### 4.7 Auth

**None.** The service assumes it sits behind Macrowise's gateway. If that
changes, add an API-key header check at the top of `api/main.py` or drop a
middleware. The endpoint surface is idempotent and read-only from the client's
perspective, so a single shared secret is sufficient.

### 4.8 Python library (in-process, no HTTP)

```python
from macrowise import MonteCarloConfig, MonteCarlo

config = MonteCarloConfig(
    initial_balance=1_000_000,
    years=30,
    simulations=1000,
    assets=[
        ("NIFTY_50", 0.60),
        ("NIFTY_MIDCAP_150", 0.40),
    ],
    model=1,
    bootstrap_model=1,
    seed=42,
)

results = MonteCarlo(config).run()

print(f"Median CAGR:     {results.median_cagr:.2%}")
print(f"Success rate:    {results.success_rate:.1%}")
print(f"Median terminal: Rs {results.median_final_balance:,.0f}")
print(f"SWR:             {results.swr:.2%}")
print(f"PWR:             {results.pwr:.2%}")
```

The Python API returns pandas DataFrames for the tables and numpy arrays for
the raw paths (`results.balance_paths`, `results.return_paths`). The HTTP API
serialises everything to plain JSON.

---

## 5. The Request Schema

Every field is optional except `assets` when weights do not sum to 1.0.
Unrecognised fields are rejected with HTTP 422 (`extra="forbid"` on every
Pydantic model).

### 5.1 Core

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `initial_balance` | `float` | `1_000_000` | `> 0` | Starting portfolio value in INR. |
| `years` | `int` | `30` | `[1, 100]` | Simulation horizon in years. |
| `simulations` | `int` | `1000` | `[10, 10000]` | Number of Monte Carlo paths. Higher = smoother tails. When using the Python library directly (`MonteCarloConfig`), the default is `10_000` — the HTTP schema overrides this to `1_000` for faster response times. |
| `assets` | `list[AssetAllocation]` | `[NIFTY_50: 0.60, NIFTY_MIDCAP_150: 0.40]` | Weights sum to `1.0` (± 0.001) | Portfolio composition. See 5.9. |
| `seed` | `int` | `42` | any | RNG seed. Same seed + same request = identical output. |

### 5.2 Simulation model

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `model` | `int` | `1` | `{1, 2, 3, 4}` | `1`=Historical, `2`=Statistical, `3`=Parameterized, `4`=Forecasted GARCH. |
| `time_series_model` | `int` | `1` | `{1, 3}` | For `model=4`: `1`=Normal, `3`=GARCH. |
| `distribution_type` | `int` | `1` | `{1, 2}` | For `model=3`: `1`=Normal, `2`=Student-t fat-tailed. |
| `degrees_of_freedom` | `int` | `30` | `[5, 50]` | d.o.f. for the Student-t (used when `distribution_type=2`). |

### 5.3 Historical bootstrap (used by models 1 & 2)

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `bootstrap_model` | `int` | `1` | `{0, 1, 2}` | `0`=Single-Month, `1`=Single-Year, `2`=Block. |
| `bootstrap_min_years` | `int` | `1` | `[1, 30]` | Minimum block length in years (Block only). |
| `bootstrap_max_years` | `int` | `20` | `[1, 30]` | Maximum block length in years (Block only). |
| `circular_bootstrap` | `bool` | `true` | — | Wrap-around at end of history. Affects Block sampling only. |

### 5.4 History window

| Field | Type | Default | Notes |
|---|---|---|---|
| `use_full_history` | `bool` | `true` | If `true`, ignores `start_year` / `end_year`. |
| `start_year` | `int \| null` | `null` | Restrict historical window (inclusive). |
| `end_year`   | `int \| null` | `null` | Restrict historical window (inclusive). |

### 5.5 Custom parameters (models 2 & 3)

| Field | Type | Default | Notes |
|---|---|---|---|
| `historical_volatility` | `bool` | `true` | If `true`, use historical σ; else `custom_stds`. |
| `historical_correlations` | `bool` | `true` | If `true`, use historical ρ; else identity or `custom_correlation`. |
| `custom_means` | `list[float] \| null` | `null` | Annual mean return per asset. Length must equal `assets`. |
| `custom_stds` | `list[float] \| null` | `null` | Annual std dev per asset. Length must equal `assets`. |
| `custom_correlation` | `list[list[float]] \| null` | `null` | n×n correlation matrix. Model 3 only. |

### 5.6 Rebalancing

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `rebalance_frequency` | `int` | `1` | `{0, 1, 2, 3, 4}` | `0`=None, `1`=Annual, `2`=Semi-Annual, `3`=Quarterly, `4`=Monthly. |

### 5.7 Inflation

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `inflation_adjusted` | `bool` | `true` | — | Return real (inflation-adjusted) metrics alongside nominal. |
| `inflation_model` | `int` | `1` | `{1, 2}` | `1`=Historical CPI bootstrap, `2`=Parameterized N(μ/12, σ/√12). |
| `inflation_mean` | `float` | `0.04` | `[0, 1]` | Annual mean inflation (used by model 2). |
| `inflation_volatility` | `float` | `0.03` | `[0, 1]` | Annual inflation vol (used by model 2). |

### 5.8 Sequence-of-returns stress

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `sequence_stress_test` | `int` | `0` | `[0, 10]` | Place N worst historical years first. `0` disables. |

### 5.9 Portfolio (`AssetAllocation`)

```jsonc
{
  "asset": "NIFTY_50",     // Alias from GET /assets or GET /assets/search
  "weight": 0.60           // In [0, 1]. All weights across the list must sum to 1.0 ± 0.001.
}
```

### 5.10 Cash flows

Every cashflow field is optional. If `cashflow_type` is `null` or `0`, no
cashflow schedule is applied. See Section 9 for what each type does.

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `cashflow_type` | `int \| null` | `null` | `{0, 1, 2, 3, 4, 8, 9}` | `0`=None, `1`=Contribute, `2`=Withdraw, `3`=Fixed-%, `4`=Life-expectancy, `8`=Fixed+PctChange, `9`=Contribute+PctChange. Types `5` (rolling avg) and `6` (Guyton-Klinger) are not implemented and return HTTP 500. |
| `cashflow_amount` | `float \| null` | `null` | — | Amount per period in INR (used by types 1, 2, 4, 8, 9). |
| `cashflow_frequency` | `"monthly" \| "quarterly" \| "annual" \| null` | `null` | — | Frequency for the amount. |
| `withdrawal_percentage` | `float \| null` | `null` | `[0, 100]` | For type 3: percent of current balance to withdraw each period. |
| `rolling_periods` | `int \| null` | `null` | `[2, 5]` | For type 5 (not implemented). |
| `smoothing_rate` | `float \| null` | `null` | `[0.5, 0.9]` | For type 6 (not implemented). |
| `life_expectancy_model` | `"single" \| "uniform" \| null` | `null` | — | For type 4. |
| `current_age` | `int \| null` | `null` | `[30, 95]` | For type 4. |

### 5.11 Rates & output tuning

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `risk_free_rate` | `float` | `0.0483` | `[0, 1]` | Annualised risk-free rate used by Sharpe and Sortino. |
| `percentiles` | `list[float]` | `[0.10, 0.25, 0.50, 0.75, 0.90]` | each in `(0, 1)` | Percentile levels for balance tables. |

### 5.12 Reserved / not yet wired

| Field | Type | Default | Notes |
|---|---|---|---|
| `return_intervals` | `list[float]` | `[0, 0.025, 0.05, 0.075, 0.10, 0.125]` | Accepted by the API schema but not wired into the engine. The expected-returns table uses its own hardcoded thresholds. |
| `tax_enabled` | `bool` | `false` | Sets HTTP 400 with `"tax_enabled is not yet implemented"` if true. The `IndianTaxCalculator` module is present but not wired into the simulation loop. |

---

## 6. The Response Schema

Every numeric value is a raw `float` — no pre-formatted strings, no
locale-specific separators. The client formats as it wishes.

### 6.1 Top-level structure

```jsonc
{
  // ── Run metadata ───────────────────────────────────────────────────
  "n_simulations": 1000,
  "n_years": 30,
  "assets": [
    {"alias": "NIFTY_50",         "name": "Nifty 50",           "weight": 0.60},
    {"alias": "NIFTY_MIDCAP_150", "name": "Nifty Midcap 150",   "weight": 0.40}
  ],
  "config_echo": { /* the full request, echoed back */ },

  // ── Headline KPIs (scalars) ────────────────────────────────────────
  "median_cagr":            0.1330,     // Decimal, e.g. 13.30 %
  "success_rate":           1.000,      // Fraction of paths ending > 1 % of initial
  "median_final_balance":   42658924.0, // INR
  "swr":                    0.0150,     // Safe Withdrawal Rate (>=95 % survival)
  "pwr":                    0.0150,     // Perpetual Withdrawal Rate

  // ── Tables ─────────────────────────────────────────────────────────
  "performance_summary": { /* 9 stats × 5 percentiles — see 6.2 */ },
  "balance_percentiles": { /* year → 5-percentile band — see 6.3 */ },
  "expected_returns":    { /* threshold → horizon → probability — see 6.4 */ },
  "loss_probabilities":  { /* threshold → horizon → probability — see 6.4 */ },
  "simulated_assets":    { /* per-asset correlations + realised metrics — see 6.5 */ },

  // ── Distribution details ───────────────────────────────────────────
  "terminal_distribution": { "bin_edges": [ ... 51 floats ... ],
                             "bin_counts": [ ... 50 ints ... ] },
  "drawdown_percentiles":  { "p10": -0.8838, "p25": -0.7985, "p50": -0.6659,
                             "p75": -0.6123, "p90": -0.3870 }
}
```

### 6.2 `performance_summary`

9 stats × 5 percentiles. Every row is a `{p10, p25, p50, p75, p90}` band. All
values are decimals (returns are fractions of 1; balances are INR).

```jsonc
{
  "time_weighted_return_nominal":  { "p10": 0.07, "p25": 0.10, "p50": 0.13, "p75": 0.16, "p90": 0.19 },
  "time_weighted_return_real":     { ... },     // Nominal minus inflation, path-by-path
  "portfolio_end_balance_nominal": { ... },     // INR terminal value
  "portfolio_end_balance_real":    { ... },
  "annual_mean_return":            { ... },     // Arithmetic mean of annual returns
  "annualized_volatility":         { ... },     // sqrt(12) * monthly std
  "sharpe_ratio":                  { ... },     // (r - rf) / sigma, annualised
  "sortino_ratio":                 { ... },     // Downside-only denominator, target=0
  "maximum_drawdown":              { ... }      // Negative decimal, e.g. -0.4212 = -42.12 %
}
```

### 6.3 `balance_percentiles`

Year (as string, `"0"` through `"n_years"`) → `{p10, p25, p50, p75, p90}`.
Year `"0"` equals `initial_balance` across all five bands.

### 6.4 `expected_returns` and `loss_probabilities`

Threshold string → horizon-year string → probability in `[0, 1]`, or `null`
if the horizon exceeds the simulation length.

```jsonc
"expected_returns": {
  ">= 0%":   { "1": 0.72, "3": 0.81, "5": 0.86, "10": 0.93, "15": 0.96,
               "20": 0.98, "25": 0.99, "30": 0.99 },
  ">= 2%":   { ... },
  ">= 5%":   { ... },
  ">= 8%":   { ... },
  ">= 10%":  { ... },
  ">= 12%":  { ... },
  ">= 15%":  { ... }
}
```

`loss_probabilities` uses labels of the form `">= 2.5%"` — meaning
"probability of a **loss** of at least 2.5 % (annualised)". Not `<= -2.5 %`.

### 6.5 `simulated_assets`

Per-asset row. Keys: correlations to every other asset in the portfolio (using
the asset display name, lowercased and snake-cased), plus `cagr`,
`expected_return`, `volatility`.

```jsonc
"simulated_assets": {
  "Nifty 50": {
    "nifty_50":         1.0,
    "nifty_midcap_150": 0.905,
    "cagr":             0.1221,
    "expected_return":  0.1360,
    "volatility":       0.2090
  },
  "Nifty Midcap 150": { ... }
}
```

### 6.6 `terminal_distribution`

Real histogram of the final-balance vector across all simulation paths. Not a
fitted Gaussian — actual bin counts from `numpy.histogram(final_balances, bins=50)`.

```jsonc
{
  "bin_edges":  [ 1_234_567.0, 2_345_678.0, ..., 987_654_321.0 ],  // length 51
  "bin_counts": [ 3, 8, 21, 47, 89, ..., 2 ]                       // length 50, sums to n_simulations
}
```

### 6.7 `drawdown_percentiles`

`{p10, p25, p50, p75, p90}` of the max drawdown across all paths. All values
are negative decimals (`-0.42` = -42 %).

### 6.8 `config_echo`

The full parsed request, echoed back. Use this to audit exactly what ran
(defaults are visible here), and to compare two runs.

---

## 7. 12 Worked Examples With Real Results

Every example below can be reproduced against a running server with `curl`, or
by feeding the payload to the Python library. **The numbers are from real runs
against the current pickle set** (fixed `seed`, so they reproduce exactly).

All balances in INR. Percentages are shown as either decimals (e.g. `0.133`)
or converted to percent for readability (e.g. `13.3 %`).

---

### Example 01 — Default balanced portfolio (60/40 large + mid)

30-year horizon, 60 % Nifty 50 + 40 % Nifty Midcap 150, historical bootstrap,
annual rebalance, inflation-adjusted.

```json
{
  "initial_balance": 1000000,
  "years": 30,
  "simulations": 1000,
  "assets": [
    {"asset": "NIFTY_50", "weight": 0.60},
    {"asset": "NIFTY_MIDCAP_150", "weight": 0.40}
  ],
  "model": 1, "bootstrap_model": 1,
  "rebalance_frequency": 1, "inflation_adjusted": true, "seed": 42
}
```

| Metric | Value |
|---|---|
| Median CAGR | 13.30 % |
| Success rate | 100.0 % |
| Median terminal balance | ₹4.27 Cr |
| SWR / PWR | 1.50 % |
| Vol (p50) | 21.9 % |
| Sharpe (p50) | 0.47 |
| Max drawdown (p50) | -64.0 % |
| Year-30 balance p10 / p50 / p90 | ₹40.3 L / ₹4.27 Cr / ₹32.7 Cr |

**Reading it:** the median outcome is a 42× nominal growth over 30 years — in
line with Indian equity's ~13 % long-run CAGR. The p10 outcome (₹40.3 L) still
outperforms fixed deposits, and the p90 outcome (₹32.7 Cr) illustrates the
right-skew of compounding. The 21.9 % vol and -64 % worst-case drawdown are
the honest cost.

---

### Example 02 — Step-up SIP: ₹25k/month growing 10%/yr into Nifty 500 for 25 years

Block bootstrap with 3–10 year blocks (preserves regime clustering).
Cashflow type 9 = contribution with annual step-up.

```json
{
  "initial_balance": 100000,
  "years": 25,
  "simulations": 1000,
  "assets": [{"asset": "NIFTY_500", "weight": 1.0}],
  "model": 1, "bootstrap_model": 2,
  "bootstrap_min_years": 3, "bootstrap_max_years": 10,
  "cashflow_type": 9, "cashflow_amount": 25000, "cashflow_frequency": "monthly",
  "pct_change": 0.10,
  "inflation_adjusted": true, "seed": 7
}
```

| Metric | Value |
|---|---|
| Median CAGR | 11.5 % |
| Success rate | 100.0 % |
| Median terminal balance | ₹5.71 Cr |
| Year-25 balance p10 / p50 / p90 | ₹2.67 Cr / ₹5.71 Cr / ₹12.9 Cr |
| Max drawdown (p50) | -58.9 % |

**Reading it:** total contributed over 25 years is ₹1 L + 300 × ₹25k = ₹76 L.
The median outcome (₹5.71 Cr) is a ~7.5× multiple of that. The 10-year block
bootstrap preserves the "hot decade, cold decade" dynamic — you can see the
range in the p10–p90 spread.

---

### Example 03 — Retirement SWP: ₹40k/month from ₹2 Cr for 30 years

Diversified equity (Nifty 50 / Midcap / Smallcap = 60/25/15), inflation-adjusted
withdrawals.

```json
{
  "initial_balance": 20000000,
  "years": 30,
  "simulations": 1000,
  "assets": [
    {"asset": "NIFTY_50", "weight": 0.60},
    {"asset": "NIFTY_MIDCAP_150", "weight": 0.25},
    {"asset": "NIFTY_SMALLCAP_250", "weight": 0.15}
  ],
  "model": 1, "bootstrap_model": 1,
  "cashflow_type": 2, "cashflow_amount": 40000, "cashflow_frequency": "monthly",
  "rebalance_frequency": 1, "inflation_adjusted": true, "seed": 42
}
```

| Metric | Value |
|---|---|
| Median CAGR | 13.1 % |
| Success rate | 89.3 % |
| Median terminal balance | ₹55.2 Cr |
| Year-30 balance p10 | **₹0** (portfolio depleted) |
| Year-30 balance p90 | ₹509.7 Cr |
| Max drawdown (p50) | -66.1 % |

**Reading it:** the median retiree ends up with far more than they started
with — but ~11 % of paths deplete the corpus before year 30. That's the tail
the SWR calculation targets: at ₹40k/month = ₹4.8 L/year on a ₹2 Cr corpus,
you're withdrawing 2.4 % nominally, which is well below the engine's computed
SWR (1.5 %) once inflation is baked in over 30 years.

---

### Example 04 — Parametric fat-tail: Student-t returns (df=10)

20-year horizon, 70 % Nifty 500 + 30 % Nifty 50, Model 3 with heavier tails
than Normal.

```json
{
  "initial_balance": 1000000,
  "years": 20,
  "simulations": 1000,
  "assets": [
    {"asset": "NIFTY_500", "weight": 0.70},
    {"asset": "NIFTY_50", "weight": 0.30}
  ],
  "model": 3, "distribution_type": 2, "degrees_of_freedom": 10,
  "historical_volatility": true, "historical_correlations": true,
  "rebalance_frequency": 1, "seed": 42
}
```

| Metric | Value |
|---|---|
| Median CAGR | 12.2 % |
| Success rate | 100.0 % |
| Median terminal balance | ₹1.01 Cr |
| Year-20 balance p10 / p50 / p90 | ₹27.8 L / ₹1.01 Cr / ₹3.79 Cr |
| Max drawdown (p50) | -44.2 % |

**Reading it:** compared with a Normal-distribution run of the same portfolio,
`df=10` produces a slightly wider p10–p90 spread. The Sharpe (0.41) is lower
than the historical-bootstrap version because Model 3 draws from a synthetic
distribution rather than the actual return series, losing some of the
correlation-and-clustering structure that boosts realised Sharpe.

---

### Example 05 — GARCH-forecasted volatility (Model 4)

15-year horizon, 3-asset mix, GARCH(1,1) with cross-asset Cholesky
correlation.

```json
{
  "initial_balance": 1000000,
  "years": 15,
  "simulations": 1000,
  "assets": [
    {"asset": "NIFTY_50", "weight": 0.50},
    {"asset": "NIFTY_MIDCAP_150", "weight": 0.30},
    {"asset": "NIFTY_IT", "weight": 0.20}
  ],
  "model": 4, "time_series_model": 3,
  "rebalance_frequency": 1, "seed": 42
}
```

| Metric | Value |
|---|---|
| Median CAGR | 13.6 % |
| Success rate | 100.0 % |
| Median terminal balance | ₹67.98 L |
| Vol (p50) | 21.4 % |
| Sharpe (p50) | 0.48 |
| Max drawdown (p50) | -38.7 % |

**Reading it:** GARCH creates volatility clustering that a plain Normal draw
misses. Compared to a Model 3 Normal run of the same portfolio, GARCH's
median drawdown is slightly deeper because a bad month is more likely to be
followed by more bad months.

---

### Example 06 — Sequence-of-returns stress test

Same base 60/40 portfolio as Example 01, but the 5 worst historical years are
forcibly placed at the start of every simulated path.

```json
{
  "initial_balance": 1000000,
  "years": 30,
  "simulations": 1000,
  "assets": [
    {"asset": "NIFTY_50", "weight": 0.60},
    {"asset": "NIFTY_MIDCAP_150", "weight": 0.40}
  ],
  "model": 1, "bootstrap_model": 1,
  "sequence_stress_test": 5,
  "rebalance_frequency": 1, "inflation_adjusted": true, "seed": 42
}
```

| Metric | Value |
|---|---|
| Median CAGR | 13.3 % (same total return distribution) |
| Median terminal balance | ₹4.27 Cr (same) |
| **SWR** | **0.0 %** (down from 1.5 %) |
| Max drawdown (p50) | **-84.1 %** (vs -64.0 % baseline) |

**Reading it:** total-return distribution is unchanged (the same returns just
happen in a different order), but withdrawal-survival collapses because a
withdrawing portfolio that crashes early has less capital left to compound
back. This is the "sequence-of-returns risk" — the number that matters for a
retiree, not the average CAGR.

---

### Example 07 — Sectoral mix (Bank / IT / Pharma / FMCG / Auto)

20-year horizon, ₹50 L initial, 5-sector equal-ish blend.

```json
{
  "initial_balance": 5000000,
  "years": 20,
  "simulations": 1000,
  "assets": [
    {"asset": "NIFTY_BANK",   "weight": 0.25},
    {"asset": "NIFTY_IT",     "weight": 0.20},
    {"asset": "NIFTY_PHARMA", "weight": 0.15},
    {"asset": "NIFTY_FMCG",   "weight": 0.20},
    {"asset": "NIFTY_AUTO",   "weight": 0.20}
  ],
  "model": 1, "bootstrap_model": 1,
  "rebalance_frequency": 1, "inflation_adjusted": true, "seed": 42
}
```

| Metric | Value |
|---|---|
| Median CAGR | 15.7 % |
| Success rate | 100.0 % |
| Median terminal balance | ₹9.16 Cr |
| Vol (p50) | 18.4 % |
| Sharpe (p50) | 0.63 |
| Max drawdown (p50) | -44.5 % |

**Reading it:** cross-sector diversification (bank + IT + pharma + FMCG + auto)
lowers vol from 22 % (large-cap only) to 18 %, and lifts the median Sharpe.
Because these sectors are not perfectly correlated, the p50 drawdown is
shallower than the broad-index case.

---

### Example 08 — Factor-index blend (Alpha, Momentum, Quality, Low-Vol)

20-year horizon, equal-weight across 4 factor indices.

```json
{
  "initial_balance": 1000000,
  "years": 20,
  "simulations": 1000,
  "assets": [
    {"asset": "NIFTY_ALPHA_50",         "weight": 0.25},
    {"asset": "NIFTY200_MOMENTUM_30",   "weight": 0.25},
    {"asset": "NIFTY100_QUALITY_30",    "weight": 0.25},
    {"asset": "NIFTY_LOW_VOLATILITY_50","weight": 0.25}
  ],
  "model": 1, "bootstrap_model": 1,
  "rebalance_frequency": 1, "inflation_adjusted": true, "seed": 42
}
```

| Metric | Value |
|---|---|
| Median CAGR | 15.3 % |
| Median terminal balance | ₹1.74 Cr |
| Vol (p50) | 15.5 % |
| Sharpe (p50) | 0.69 |
| Max drawdown (p50) | -28.4 % |

**Reading it:** factor diversification produces the highest Sharpe of the 12
examples (0.69) and the shallowest median drawdown (-28 %). Low-vol is
suppressing tail risk; Alpha and Momentum are lifting the mean.

---

### Example 09 — Concentrated 3-stock bet (Reliance / TCS / HDFC Bank)

15-year horizon, three large-cap flagships.

```json
{
  "initial_balance": 1000000,
  "years": 15,
  "simulations": 1000,
  "assets": [
    {"asset": "RELIANCE", "weight": 0.40},
    {"asset": "TCS",      "weight": 0.30},
    {"asset": "HDFCBANK", "weight": 0.30}
  ],
  "model": 1, "bootstrap_model": 1,
  "rebalance_frequency": 1, "inflation_adjusted": true, "seed": 42
}
```

| Metric | Value |
|---|---|
| Median CAGR | 24.6 % |
| Median terminal balance | ₹2.71 Cr |
| Vol (p50) | 21.6 % |
| Sharpe (p50) | 0.93 |
| Max drawdown (p50) | -36.0 % |
| Year-15 balance p10 / p50 / p90 | ₹55.1 L / ₹2.71 Cr / ₹10.7 Cr |

**Reading it:** three winners of the last two decades produce a much higher
Sharpe (0.93) and CAGR (24.6 %) than any index blend — but this is a
survivorship-tinted lens. The stocks in the pickle are today's Nifty 500; the
history baked in is theirs. Use this pattern for **what-if** analysis on named
holdings, not for forward-looking projections of "just pick 3 winners."

---

### Example 10 — Bengen 4 % rule from a ₹2 Cr corpus

Fixed-percentage withdrawal (type 3): 4 % of the current balance, annually,
for 30 years.

```json
{
  "initial_balance": 20000000,
  "years": 30,
  "simulations": 1000,
  "assets": [
    {"asset": "NIFTY_50", "weight": 0.70},
    {"asset": "NIFTY_MIDCAP_150", "weight": 0.30}
  ],
  "model": 1, "bootstrap_model": 1,
  "cashflow_type": 3, "withdrawal_percentage": 4.0, "cashflow_frequency": "annual",
  "rebalance_frequency": 1, "inflation_adjusted": true, "seed": 42
}
```

| Metric | Value |
|---|---|
| Median CAGR | 13.0 % |
| Success rate | 100.0 % (balance always > 1 % of initial) |
| Median terminal balance | ₹23.10 Cr |
| Year-30 balance p10 / p90 | ₹2.35 Cr / ₹160.55 Cr |

**Reading it:** taking a **percentage of current balance** (not a fixed rupee
amount) never depletes the account — the payment adjusts with the market.
That's why success is 100 % even at a 4 % rate. It's also why the terminal
balance dispersion is so wide (p10 ₹2.35 Cr vs p90 ₹160 Cr): everyone starts
with ₹2 Cr, but by year 30 the winners have compounded far past the losers.

---

### Example 11 — Fully custom parametric (Model 3, user μ / σ / ρ)

Advanced use case: user overrides all statistical parameters. The engine
draws Normal returns with the specified structure.

```json
{
  "initial_balance": 1000000,
  "years": 25,
  "simulations": 1000,
  "assets": [
    {"asset": "NIFTY_50",         "weight": 0.60},
    {"asset": "NIFTY_MIDCAP_150", "weight": 0.40}
  ],
  "model": 3, "distribution_type": 1,
  "historical_volatility": false, "historical_correlations": false,
  "custom_means":       [0.13, 0.16],
  "custom_stds":        [0.18, 0.25],
  "custom_correlation": [[1.0, 0.85], [0.85, 1.0]],
  "rebalance_frequency": 1, "seed": 42
}
```

| Metric | Value |
|---|---|
| Median CAGR | 13.0 % |
| Success rate | 100.0 % |
| Median terminal balance | ₹2.13 Cr |
| Vol (p50) | 20.0 % |
| Max drawdown (p50) | -39.0 % |

**Reading it:** with `historical_volatility=false` and
`historical_correlations=false`, the engine is running on the user's
assumptions, not the pickle. Set these to `true` and pass only
`custom_means` if you want to keep historical vol/ρ but shift the mean.

---

### Example 12 — Life-expectancy RMD schedule from age 60

Cashflow type 4: withdrawal amount computed each year as `base_amount /
life_expectancy(age+year) / 12`.

```json
{
  "initial_balance": 20000000,
  "years": 30,
  "simulations": 1000,
  "assets": [
    {"asset": "NIFTY_50",         "weight": 0.60},
    {"asset": "NIFTY_MIDCAP_150", "weight": 0.40}
  ],
  "model": 1, "bootstrap_model": 1,
  "cashflow_type": 4, "cashflow_amount": 1000000, "cashflow_frequency": "annual",
  "current_age": 60, "life_expectancy_model": "single",
  "rebalance_frequency": 1, "inflation_adjusted": true, "seed": 42
}
```

| Metric | Value |
|---|---|
| Median CAGR | 13.3 % |
| Success rate | 99.8 % |
| Median terminal balance | ₹83.12 Cr |
| Year-30 balance p10 / p50 / p90 | ₹7.15 Cr / ₹83.12 Cr / ₹647.7 Cr |

**Reading it:** the life-expectancy schedule starts small (₹1 L / 25.5-year
expectancy / 12 ≈ ₹327/month at age 60) and grows as the divisor shrinks. At
age 90 the divisor is ~4.4, so the same base amount produces ₹1,894/month.
This mirrors the US RMD rules and captures the "less risk of running out
early, more risk of leaving too much" trade-off explicitly.

---

## 8. Simulation Models — Every Model in Detail

`GET /models` returns the same information machine-readable, for LLM tool
selection.

### 8.1 Model 1 — Historical Bootstrap

Resamples from the actual monthly return history. Three sub-methods:

| `bootstrap_model` | Method | Preserves |
|---|---|---|
| `0` | Single-Month | Cross-asset correlation each month |
| `1` | Single-Year  | Cross-asset correlation + intra-year serial structure |
| `2` | Block        | Cross-asset correlation + serial structure over N-year blocks |

`circular_bootstrap=true` lets the block sampler wrap around the end of
history. `bootstrap_min_years` / `bootstrap_max_years` bound the block length.

Fat tails, autocorrelation, and cross-asset dependency are captured naturally
because the samples are drawn from real history.

### 8.2 Model 2 — Statistical (Bootstrap + Rescale)

Runs Model 1 first, then rescales each asset's returns to match user-supplied
`custom_means` and/or `custom_stds`. Useful when you want "historical shape,
but with mean N %".

Rescale formula (monthly): `r' = ((r - hist_mean) * (target_std/hist_std)) + target_mean`.

### 8.3 Model 3 — Parameterized (Normal or Student-t)

Synthetic monthly returns from a chosen parametric distribution:

- `distribution_type=1` → multivariate Normal via `numpy.random.default_rng().multivariate_normal`.
- `distribution_type=2` → Student-t copula built from a standard-t draw
  ÷ `sqrt(dof/(dof-2))` (unit variance), correlated via Cholesky decomposition
  of the correlation matrix, then scaled by monthly σ and shifted by monthly μ.

Correlation is either historical or from `custom_correlation`. Fat tails
require `distribution_type=2`.

### 8.4 Model 4 — Forecasted (GARCH(1,1))

Volatility clusters. Each asset follows

```
σ_t² = ω + α · r²_{t-1} + β · σ²_{t-1}
r_t  = μ_m + σ_t · z_t
```

with `α=0.08`, `β=0.90` by default (`α + β = 0.98`, high persistence typical
of daily equity), and `ω = σ_initial² · (1 - α - β)`. Cross-asset correlation
is imposed via Cholesky decomposition on the `z_t` draws before scaling.

If `time_series_model=1`, the engine falls back to plain Normal draws (i.e.
Model 3 Normal path).

### 8.5 Model capability matrix

| id | Name | Bootstrap | Custom μ/σ | Custom ρ | Fat tails | GARCH |
|----|------|:---------:|:----------:|:--------:|:---------:|:-----:|
| 1  | Historical       | ✓ | – | – | – | – |
| 2  | Statistical      | ✓ | ✓ | – | – | – |
| 3  | Parameterized    | – | ✓ | ✓ | ✓ | – |
| 4  | Forecasted       | – | ✓ | ✓ | – | ✓ |

`GET /models` returns this as JSON with `recommended_when` copy for each.

---

## 9. Cash Flow Types

Implemented in `macrowise/engine/cashflow.py`. The engine builds a per-month
schedule and applies it inside the simulation loop.

| Type | Name | What it does |
|---|---|---|
| `0` | None | No cashflow. Same as omitting the block entirely. |
| `1` | Contribute | Adds `cashflow_amount` per period (spread across assets by weight). |
| `2` | Withdraw | Subtracts `cashflow_amount` per period. Withdrawal is capped at current balance. |
| `3` | Fixed % | Withdraws `withdrawal_percentage` of the current balance per period. Never depletes to exactly zero (adjusts each period). |
| `4` | Life Expectancy | RMD-style: monthly withdrawal = `cashflow_amount / life_expectancy(age+year) / 12`. Uses IRS distribution period table for ages 30–95. |
| `5` | Rolling Average | **Not implemented — returns HTTP 500.** |
| `6` | Guyton-Klinger (geometric) | **Not implemented — returns HTTP 500.** |
| `8` | Fixed withdrawal + pct change | Type 2 with an annual percentage step-up. Pass `pct_change` (e.g. `0.05` for 5% yearly increase in amount). |
| `9` | Contribution + pct change | Type 1 with an annual step-up (SIP top-up). Pass `pct_change` to control the yearly increase rate. |

`cashflow_frequency` is `"monthly"`, `"quarterly"`, or `"annual"`. Combined
with `cashflow_amount`, the engine produces the per-month schedule.

Inflation-adjusted cashflows scale the amount up by cumulative inflation, so
"₹40k/month" grows in nominal terms year-on-year to hold real purchasing power.

---

## 10. Historical Data

### 10.1 What's in the pickle

`data/processed/all_monthly_returns_final.pkl` contains 318 monthly return
observations across 719 assets. Coverage varies by asset — many older indices
have full history from 2000; several newer factor indices only from 2020.

The 719 assets break down as:

- **Broad-market and large-cap NSE/BSE indices**: Nifty 50, Nifty 100, Nifty
  200, Nifty 500, Nifty Total Market, BSE Sensex, BSE 100/200/500/AllCap,
  Nifty Bank, IT, Pharma, FMCG, Auto, Metal, Realty, Media, Financial
  Services, etc.
- **Mid- and small-cap indices**: Nifty Midcap 50/100/150, Nifty Smallcap
  50/100/250, Nifty Microcap 250, BSE 150 Midcap, BSE 250 Smallcap, BSE
  Microcap.
- **Factor / thematic indices**: Alpha 50, Momentum 30, Quality 30, Low-Vol
  50, Value 20, Dividend Leaders, Shariah, ESG, PSU Bank, Private Bank, etc.
- **500 Nifty 500 constituent stocks** — Reliance, TCS, Infosys, HDFC Bank,
  ICICI Bank, and so on.
- **INDIA_VIX** (volatility index).

`GET /assets` returns the full list with categories. `GET /assets/search?q=`
does substring search.

### 10.2 Other pickle files

- `all_prices_final.pkl` — daily prices.
- `all_annual_returns_final.pkl` — 27 years of annual returns.
- `all_asset_statistics_final.pkl` — per-asset `mean_annual`, `std_annual`,
  and 11 other precomputed metrics.
- `all_correlation_matrix_final.pkl` — Pearson correlation of monthly returns.
- `all_covariance_matrix_final.pkl` — annualised covariance.
- `inflation_data.pkl` — CPI index levels (used by inflation model 1).
- `dynamic_risk_free_rate.pkl` — RBI-repo-based rate series.
- `life_expectancy_india.pkl` — SRS 2016-20 life-expectancy table.

### 10.3 What's not in the pickle

**No debt / gilt / gold / real-estate series.** The 719 assets are entirely
equity. Any request that references `SBI_GILT`, `GOLD`, or similar
(references from a previous data snapshot) will return HTTP 400 with the
`Unknown asset` error and a list of the closest 20 aliases.

If a fixed-income sleeve becomes important, the pickle would need to be
regenerated to include debt indices (Nifty gilt indices, corporate bond
indices, etc.).

---

## 11. Test Coverage

`tests/test_api_exhaustive.py` runs 153 test cases against the in-process
FastAPI app via `TestClient`. Every category:

- All 4 simulation models × all bootstrap sub-methods × circular on/off.
- All 5 rebalance frequencies.
- All 4 inflation configurations.
- All values of `sequence_stress_test` from 0 to 10 (spot-checked).
- Every implemented cashflow type (0, 1, 2, 3, 4, 8, 9).
- Types 5 and 6 asserted to return HTTP 500 (`NotImplementedError`).
- Custom means / custom stds / custom correlation matrices (all shapes).
- History window filters (`start_year`, `end_year`, `use_full_history`).
- Portfolio compositions: single asset, 4-asset factor blend, 5-sector mix,
  concentrated 3-stock stack.
- Horizons: 1 / 5 / 30 / 50 / 100 years.
- Simulation counts: 10 / 100 / 1000 / 5000.
- Determinism (same seed = same output; different seed = different).
- All error paths: bad weights, unknown asset, `tax_enabled=true`, out-of-range
  fields, extra fields.
- Numeric-sense checks: SIP grows > initial, heavy SWP fails more than none,
  fat-tail has wider p10–p90 than Normal, `config_echo` round-trips.

Run:

```bash
PYTHONPATH=. python tests/test_api_exhaustive.py
```

Expected output ends with `Results: 153 passed, 0 failed`.

---

## 12. Frontend Integration Notes

### 12.1 TypeScript type generation (recommended)

The OpenAPI spec at `/openapi.json` is machine-readable. Generate TypeScript
interfaces so the frontend gets compile-time type safety:

```bash
# Install once
npm install -g openapi-typescript

# Regenerate whenever the backend schema changes
npx openapi-typescript http://localhost:8000/openapi.json -o src/types/macrowise-mc.d.ts
```

Then in your frontend code:

```typescript
import type { components } from '../types/macrowise-mc'

type SimulateRequest  = components['schemas']['SimulateRequest']
type SimulateResponse = components['schemas']['SimulateResponse']

const body: SimulateRequest = {
  initial_balance: 1_000_000,
  years: 30,
  simulations: 1000,
  assets: [
    { asset: 'NIFTY_50',         weight: 0.60 },
    { asset: 'NIFTY_MIDCAP_150', weight: 0.40 },
  ],
  model: 1,
  bootstrap_model: 1,
  seed: 42,
}

const res = await fetch(`${API_BASE}/simulate`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

if (!res.ok) {
  const err = await res.json()
  throw new Error(err.detail ?? err.error)
}

const data: SimulateResponse = await res.json()
// data.median_cagr, data.balance_percentiles, etc. are fully typed
```

### 12.2 Rendering the fan chart

`balance_percentiles` maps year → `{p10, p25, p50, p75, p90}`. Convert to five
line-chart series (one per percentile) and shade between them:

```typescript
const years = Object.keys(data.balance_percentiles).map(Number).sort((a, b) => a - b)
const p10 = years.map(y => data.balance_percentiles[y].p10)
const p50 = years.map(y => data.balance_percentiles[y].p50)
const p90 = years.map(y => data.balance_percentiles[y].p90)
// Shade p10↔p90 in a light colour, p25↔p75 darker, p50 as the median line.
```

### 12.3 Rendering the terminal-wealth histogram

The response contains **real histogram data**, not a fitted Gaussian:

```typescript
const { bin_edges, bin_counts } = data.terminal_distribution
// bin_edges is length 51, bin_counts is length 50 (edges[i], edges[i+1]) → counts[i]
// Feed directly to any bar chart, or use edges as x-axis labels.
```

### 12.4 INR number formatting

The API returns raw floats. Format for display client-side:

```typescript
function formatINR(n: number): string {
  if (n >= 1e7)  return `₹${(n / 1e7).toFixed(2)} Cr`
  if (n >= 1e5)  return `₹${(n / 1e5).toFixed(2)} L`
  if (n >= 1e3)  return `₹${(n / 1e3).toFixed(1)} K`
  return `₹${Math.round(n)}`
}
```

### 12.5 Error handling

All errors return `{"error": "...", "detail": "..."}`. The `detail` string is
safe to surface directly. For 422 validation errors, `detail` is an array of
Pydantic error records — pick `detail[0].msg` for a concise message or walk
the array to build a field-level error map.

```typescript
async function callSimulate(body: SimulateRequest): Promise<SimulateResponse> {
  const res = await fetch(`${API_BASE}/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (res.status === 400) {
    const { detail } = await res.json()
    throw new UserError(detail)  // Show to user directly
  }
  if (res.status === 422) {
    const { detail } = await res.json()
    // detail is Array<{loc, msg, type, ...}>
    const msg = detail.map(d => `${d.loc.slice(1).join('.')}: ${d.msg}`).join('\n')
    throw new UserError(`Invalid request:\n${msg}`)
  }
  if (!res.ok) {
    throw new Error(`API error ${res.status}`)
  }
  return res.json()
}
```

### 12.6 Common pitfalls

- **Weights must sum to exactly 1.0** (± 0.001). Rounding percentages in the
  UI can drift — normalise before sending: `w /= sum(w)`.
- **Percentages vs decimals.** The API takes decimals (`0.10` = 10 %). Convert
  in the UI edge, not in the middle of the payload.
- **`inflation_adjusted=true` doesn't change `median_cagr`.** `median_cagr`
  is always nominal; inflation shows up in `performance_summary.time_weighted_return_real`
  and `performance_summary.portfolio_end_balance_real`. Show both to the user
  or make it clear which is which.
- **Unknown fields fail with 422** (`extra="forbid"`). If you add a UI toggle
  that has no schema mapping, the whole request rejects — thread the UI to
  the schema explicitly.
- **Some cells in `expected_returns` / `loss_probabilities` are `null`.**
  Horizons beyond `n_years` cannot be evaluated. Render `null` cells as an
  em-dash or hide them.
- **`success_rate` is not "profit rate"** — it's the fraction of paths that
  ended above 1 % of the initial balance. A withdrawal simulation with
  success 89 % means 11 % of paths depleted the corpus.

### 12.7 Full working curl examples

```bash
# 1. Basic simulation (60/40 large + mid)
curl -s -X POST http://localhost:8000/simulate \
  -H 'Content-Type: application/json' \
  -d '{
    "initial_balance": 1000000,
    "years": 30,
    "simulations": 1000,
    "assets": [
      {"asset": "NIFTY_50", "weight": 0.60},
      {"asset": "NIFTY_MIDCAP_150", "weight": 0.40}
    ],
    "model": 1, "bootstrap_model": 1, "seed": 42
  }' | python -m json.tool

# 2. Search for large-cap indices
curl -s 'http://localhost:8000/assets/search?q=nifty%20large&limit=10' | python -m json.tool

# 3. See the model capability matrix
curl -s 'http://localhost:8000/models' | python -m json.tool

# 4. Grab all the example payloads Swagger uses
curl -s 'http://localhost:8000/examples' | python -m json.tool

# 5. Health probe
curl -s 'http://localhost:8000/health'

# 6. Discover every endpoint
curl -s 'http://localhost:8000/' | python -m json.tool
```

---

## 13. Known Limitations

- **Tax not wired in.** `IndianTaxCalculator` (`macrowise/engine/tax.py`) is
  implemented for FY 2024-25 rates, but the simulation loop does not consume
  it yet. `tax_enabled=true` on `/simulate` returns HTTP 400.
- **Cashflow types 5 & 6 unimplemented.** Rolling average and Guyton-Klinger
  are placeholders that raise `NotImplementedError` (surfaced as HTTP 500).
- **No debt / gilt / gold data.** The pickle is equity-only. See Section 10.
- **Glide path not exposed.** `macrowise/engine/glide_path.py` implements a
  linear career→retirement allocation glide but is not wired into
  `MonteCarloConfig` or the API.
- **`return_intervals` accepted but not wired.** The API schema accepts this field
  for custom expected-returns thresholds, but the engine uses hardcoded thresholds
  internally. Setting it has no effect.
- **Bootstrap history is finite.** With only ~26 years of monthly data, the
  single-year bootstrap has 26 unique years to draw from. Long horizons
  (e.g. 100 years) reuse the same years many times, which understates
  regime-shift risk.
- **CPI series is index levels, not rate deltas.** Inflation model 1 computes
  `pct_change()` internally; if the CPI file gets replaced with a rates file,
  the loader needs updating.
- **`data_index level/` (typo — should be `data_index_level/`) and
  `data_stocks_nifty500/` at repo root are raw source CSVs / scraping logs**,
  not required at runtime. They are kept for reproducibility of the pickle
  generation but excluded from the Docker image via `.dockerignore`.

---

## 14. Architecture Notes

**Design principles:**

- **One request → one result.** The endpoint is stateless. No sessions, no
  server-side caching. Same `seed` gives identical output every call.
- **Errors are always machine-readable JSON.** Never HTML tracebacks. The
  frontend never has to parse HTML.
- **Discoverability for LLM tool-use.** `GET /` self-describes, `GET /models`
  is a machine-readable capability matrix, `GET /examples` streams curated
  payloads, `GET /assets/search` resolves fuzzy names. An AI bot can drive
  the API end-to-end using only these endpoints for exploration and
  `POST /simulate` for the actual work.
- **Raw floats, never pre-formatted strings.** The API layer converts every
  DataFrame cell to a float (or `null`). Formatting is entirely the client's
  job.
- **`config_echo` round-trips.** Every response contains the exact request
  that produced it, so an audit trail is one HTTP call away.

**Data flow:**

```
SimulateRequest (JSON)
    │
    ▼
FastAPI validates via Pydantic v2 (extra="forbid")
    │
    ▼
api/main.py: build CashFlowConfig + MonteCarloConfig
    │
    ▼
MonteCarloSimulation._build_return_paths()  ────► (n_sims, n_months, n_assets)
    │       │
    │       ├─ Model 1: BootstrapSampler.sample_sequence()
    │       ├─ Model 2: same + rescale
    │       ├─ Model 3: NormalSampler / FatTailedSampler.generate_path()
    │       └─ Model 4: NormalSampler / GARCHSampler.generate_path()
    │
    ▼
_simulate_with_rebalance_and_cashflow()
    │       ├─ CashFlowEngine.generate_schedule(n_months)
    │       └─ per-month loop: grow → rebalance → apply cashflow → clamp
    ▼
    balance_paths (n_sims, n_months+1)  +  effective_port_returns
    │
    ▼
MonteCarloResults._compute_all()
    │       ├─ performance_summary (9×5 DataFrame)
    │       ├─ balance_percentiles (year × percentile DataFrame)
    │       ├─ expected_returns / loss_probabilities (threshold × horizon)
    │       ├─ simulated_assets (correlations + realised CAGR/Er/vol)
    │       ├─ SWR / PWR (binary search over withdrawal rates)
    │       └─ median_cagr, success_rate, median_final_balance
    │
    ▼
api/main.py: serialize DataFrames → dicts; compute histogram + drawdown percentiles
    │
    ▼
SimulateResponse (JSON)
```

**Where each concern lives:**

| Concern | Module |
|---|---|
| HTTP surface | `api/main.py` |
| Request/response schemas | `api/schemas.py` |
| Orchestration | `macrowise/engine/monte_carlo.py` |
| Historical sampling | `macrowise/engine/bootstrap.py` |
| Parametric sampling | `macrowise/engine/parametric.py` |
| Cashflow schedule | `macrowise/engine/cashflow.py` |
| Performance statistics | `macrowise/engine/stats.py` |
| Asset registry | `macrowise/data/asset_registry.py`, `_generated_index_mapping.py` |
| Data access | `macrowise/data/loader.py` |
| Deployment | `Dockerfile`, `docker-compose.yml`, `render.yaml`, `run_api.sh` |

---

## 15. Reference Cards

### 15.1 Simulation model quick pick

| Goal | Model | Sub-config |
|---|---|---|
| Default, use the actual history | 1 | `bootstrap_model=1` |
| Preserve serial correlation over multi-year regimes | 1 | `bootstrap_model=2`, `min=3 max=10` |
| "Same shape but with a different mean" | 2 | Set `custom_means`, keep `historical_volatility=true` |
| Custom correlation, Normal returns | 3 | `distribution_type=1`, set `custom_correlation`, `historical_correlations=false` |
| Fat tails | 3 | `distribution_type=2`, `degrees_of_freedom=5..15` |
| Volatility clustering | 4 | `time_series_model=3` |

### 15.2 Cashflow quick pick

| Goal | Type | Extra fields |
|---|---|---|
| Monthly SIP | `1` | `cashflow_amount`, `cashflow_frequency="monthly"` |
| SIP with annual step-up | `9` | Same as above (step-up baked into engine defaults) |
| Fixed-rupee withdrawal | `2` | `cashflow_amount`, `cashflow_frequency` |
| Bengen 4 %-rule | `3` | `withdrawal_percentage=4.0`, `cashflow_frequency="annual"` |
| RMD-style life-expectancy | `4` | `cashflow_amount`, `current_age`, `life_expectancy_model` |

### 15.3 Endpoint cheatsheet

```bash
GET  /                       # Self-describing endpoint index
GET  /health                 # Liveness
GET  /docs                   # Swagger UI
GET  /models                 # Model capability matrix
GET  /examples               # Sample payloads
GET  /assets                 # All 719 assets
GET  /assets/search?q=<>     # Fuzzy search (optional limit=, category=)
GET  /assets/{alias}         # Detail
POST /simulate               # Main endpoint — request per Section 5, response per Section 6
```

### 15.4 Minimal request

```json
{ "years": 20, "assets": [{"asset": "NIFTY_500", "weight": 1.0}] }
```

Everything else defaults.

---

*Built for Macrowise. Data window: monthly returns 1998-01 to 2024-06.
719 Indian assets across NSE and BSE.*

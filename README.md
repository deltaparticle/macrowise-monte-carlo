# Macrowise Monte Carlo Simulator

**A PortfolioVisualizer.com-style Monte Carlo simulation engine built for Indian markets.**

Simulate portfolio growth, withdrawal sustainability, and sequence-of-returns risk using historical Indian market data — NSE Total Return Indices, gilt funds, gold, and more.

**Live at**: https://macrowise-monte-carlo.onrender.com

---

## Quick Start

### Python

```python
from macrowise import MonteCarloConfig, MonteCarlo

config = MonteCarloConfig(
    initial_balance=10_00_000,   # ₹10 lakh
    years=30,
    simulations=10_000,
    assets=[
        ("NIFTY_50", 0.60),      # 60% Nifty 50 TRI
        ("SBI_GILT", 0.40),      # 40% SBI Gilt Fund
    ],
    model=1,                    # Historical bootstrap
    bootstrap_model=1,           # Single year
    seed=42,
    inflation_adjusted=False,
)

sim = MonteCarlo(config)
results = sim.run()

print(f"Median CAGR:     {results.median_cagr:.2%}")
print(f"Success Rate:    {results.success_rate:.1%}")
print(f"Median Final:    ₹{results.median_final_balance:,.0f}")
print(f"Safe Withdrawal: {results.swr:.2%}")
```

### Web UI

Visit https://macrowise-monte-carlo.onrender.com — the full web UI lets you configure a portfolio, run simulations, and view charts without writing any code.

---

## Architecture

```
macrowise/
├── engine/
│   ├── monte_carlo.py   # Simulation orchestrator
│   ├── bootstrap.py     # Historical bootstrap samplers
│   ├── parametric.py    # Statistical/parametric samplers
│   ├── cashflow.py      # Cashflow engine (SIP, withdrawals, etc.)
│   ├── stats.py         # Sharpe, Sortino, SWR, percentile computations
│   └── tax.py           # Indian tax calculator
├── data/
│   ├── loader.py        # Loads pickled DataFrames
│   └── asset_registry.py # Alias → data column mapping
└── viz/
    └── charts.py        # Matplotlib chart generation
```

**Data flow:**

```
MonteCarloConfig
       ↓
MonteCarloSimulation.run()
       ↓
   ┌───────────────────────────────────────────┐
   │  1. _generate_return_paths()              │
   │     • BootstrapSampler (historical)       │
   │     • NormalSampler / FatTailedSampler   │
   │     • GARCHSampler                       │
   └───────────────────────────────────────────┘
       ↓
   ┌───────────────────────────────────────────┐
   │  2. _generate_balance_paths()            │
   │     • Initial balance × cumulative returns │
   │     • CashFlowEngine: SIP / withdrawals    │
   │     • Rebalancing at specified frequency  │
   └───────────────────────────────────────────┘
       ↓
   ┌───────────────────────────────────────────┐
   │  3. _compute_statistics()                 │
   │     • CAGR, Sharpe, Sortino, drawdown     │
   │     • Percentile balance tables            │
   │     • SWR / PWR                           │
   │     • Loss probability table               │
   └───────────────────────────────────────────┘
       ↓
MonteCarloResults
```

---

## Monte Carlo Engine

### 4 Simulation Models

The engine implements all 4 models from PortfolioVisualizer:

| # | Model | Description | Use Case |
|---|-------|-------------|----------|
| 1 | **Historical Bootstrap** | Randomly samples actual historical monthly/yearly returns | Most realistic; respects actual market behaviour |
| 2 | **Statistical Returns** | Bootstrap + user-provided mean/std/correlation | Adjust historical data for forward-looking assumptions |
| 3 | **Parameterized Returns** | Multivariate normal or t-distribution | Theoretical scenarios; ignores fat tails with normal |
| 4 | **Forecasted Returns** | Parametric with user-provided expected return | Scenario analysis with custom return expectations |

### 3 Bootstrap Methods

For Model 1 (Historical Bootstrap):

| Method | Description | Best For |
|--------|-------------|----------|
| **Single Month** | Randomly picks one historical month at a time; cross-asset correlation preserved | Short horizons; captures intra-year volatility |
| **Single Year** | Randomly picks one full historical year at a time; preserves annual return distribution | Medium-to-long horizons; captures year-level cycles |
| **Block of Years** | Picks a contiguous block of N years; captures serial correlation and mean reversion | Long horizons; simulates multi-year bull/bear regimes |

Circular block bootstrapping wraps around the data (e.g., a 5-year block starting in 2020 wraps to 1972–1976), preventing artificial data truncation at the end of the historical range.

### Rebalancing

Portfolio is rebalanced to target weights at the specified frequency:

| Frequency | Code | Effect |
|-----------|------|--------|
| None | 0 | No rebalancing |
| Annual | 1 | Rebalance once per year |
| Semi-Annual | 2 | Twice per year |
| Quarterly | 3 | Four times per year |
| Monthly | 4 | Every month |

### Cash Flows

7 cashflow types (7 adjustment types):

| Type | Description | Sign |
|------|-------------|------|
| 0 | None | — |
| 1 | SIP / Contribution | Positive |
| 2 | Fixed Withdrawal | Negative |
| 3 | Fixed % Withdrawal | % of portfolio |
| 4 | Inflation-Adjusted Withdrawal | With CPI |
| 5 | Custom Schedule | User-provided |
| 6 | Lumpsum Contribution | One-time |

**Inflation adjustment**: When enabled, withdrawal amounts grow with a dynamic Indian CPI estimate (derived from the historical NSE data range available).

### Inflation Adjustment

Two modes:

- **Nominal returns only** — `inflation_adjusted=False`: returns and final balance are in nominal terms
- **Real returns** — `inflation_adjusted=True`: results are adjusted for Indian inflation; comparison is in today's purchasing power

The engine uses `inflation_mean` (configurable, defaults to Indian long-run inflation ~6%) as the annual inflation rate for real return computation.

---

## Data Sources

Data is stored as compressed pickle files in `data/processed/`. Total size: ~90MB across 45+ files.

### Indian Equity — NSE TRI

**Total Return Index (TRI)** = price return + dividends reinvested. This is the correct benchmark for investor returns.

| Data File | Contents |
|-----------|----------|
| `nse_tri_prices.pkl` | Daily Nifty TRI, Bank TRI, IT TRI, Pharma TRI, FMCG TRI, etc. |
| `nse_pe_pb_div.pkl` | P/E, P/B, dividend yield time series for Nifty |

**Period**: February 2000 to June 2026  
**Source**: NSE historical data, processed to TRI using dividend information

### Mutual Funds — AMFI

**AMFI** (Association of Mutual Funds in India) NAV data via `mf_nav_*` columns:

| Category | Example Assets |
|----------|---------------|
| Large Cap Equity | HDFC Top 100, ICICI Pru BlueChip |
| Mid Cap | HDFC Mid-Cap Opportunities, Motilal Oswal Midcap |
| Small Cap | SBI Small Cap, Nippon India Small Cap |
| Gilt Funds | SBI Gilt Fund (Direct), ICICI Pru Gilt Fund |
| Corporate Bond | HDFC Corporate Bond Fund, Nippon India Corporate Bond |
| Liquid / Money Market | SBI Liquid Fund, HDFC Money Market Fund |
| ELSS / Tax-Saving | ELSS funds with 3-year lock-in |

**Source**: AMFI NAV download (amfiindia.com)  
**Period**: January 2013 to June 2026

### Gold

`GOLD_INR_ETF` — Gold prices in INR, from Indian Gold ETFs  
**Source**: NSE Gold ETF NAV data  
**Period**: Matches available ETF data

### Commodities & FX

`commodities_fx.pkl` — Crude oil (WTI), INR/USD exchange rate, other commodities  
**Source**: Various Indian market data providers

### Risk-Free Rate

Dynamic risk-free rate derived from Indian G-Sec (10-year Government Bond yield), used in Sharpe ratio calculation.

### Data Pipeline

```
data_collection/
├── fetch_amfi_data.py     # Download AMFI NAV data
├── fetch_nse_data.py       # Download NSE TRI data
├── fetch_rbi_data.py      # Download RBI/SEBI data
├── collect_all_data.py     # Merge all sources
└── process_returns.py     # Compute monthly returns, statistics
```

Returns are computed as **simple monthly returns** (not log returns) to match PortfolioVisualizer's methodology:

```
monthly_return = (price_end - price_start) / price_start
```

---

## Asset Registry

The asset registry maps user-friendly aliases to actual data column names in the pickle files.

### Example Mappings

| Alias | Data Column | Name |
|-------|-------------|------|
| `NIFTY_50` | `TRI_NIFTY_50_TotalReturnsIndex` | Nifty 50 TRI |
| `SBI_GILT` | `mf_nav_MF_Gilt_SBI_GILT_FUND___DIRECT_PLAN___` | SBI Gilt Fund Direct |
| `GOLD` | `GOLD_INR_ETF` | Gold INR ETF |
| `NIFTY_BANK` | `TRI_NIFTY_BANK_TotalReturnsIndex` | Nifty Bank TRI |
| `NIFTY_IT` | `TRI_NIFTY_IT_TotalReturnsIndex` | Nifty IT TRI |
| `HDFC_TOP100` | `mf_nav_MF_Equity_HDFC_TOP_100_FUND___DIRECT_PLAN___` | HDFC Top 100 Direct |

### Usage

```python
from macrowise import get_asset, list_asset_aliases, list_categories

# List all available assets
aliases = list_asset_aliases()
print(f"Total assets: {len(aliases)}")  # 69+ assets

# List by category
categories = list_categories()
print(categories)
# ['indian_equity', 'indian_bond', 'indian_commodity', 'indian_fx', ...]

# Get asset info
info = get_asset("NIFTY_50")
print(info.name)       # "Nifty 50 TRI"
print(info.category)   # "indian_equity"
print(info.default_mean)   # 0.1506 (15.06% annual)
print(info.default_std)    # 0.2156 (21.56% annual)
```

### PortfolioVisualizer Alias Mapping

`PV_TO_INDIAN_ALIAS` maps PortfolioVisualizer asset names to Indian equivalents:

```python
from macrowise import PV_TO_INDIAN_ALIAS
print(PV_TO_INDIAN_ALIAS["TotalStockMarket"])  # "NIFTY_50"
print(PV_TO_INDIAN_ALIAS["TreasuryNotes"])     # "SBI_GILT"
print(PV_TO_INDIAN_ALIAS["Gold"])              # "GOLD"
```

This makes it easy to translate PortfolioVisualizer URLs into Macrowise configs.

### Indian Market Adaptation

| PortfolioVisualizer | Macrowise Equivalent |
|--------------------|--------------------|
| S&P 500 | Nifty 50 TRI |
| US Total Stock Market | Nifty 50 TRI (broadest available) |
| US Treasury Notes/Bonds | SBI Gilt Fund Direct / HDFC Gilt Fund |
| Corporate Investment Grade | HDFC Corporate Bond Fund |
| Gold | Gold INR ETF |
| Small Cap | SBI Small Cap Fund |
| International | Not yet available |

---

## Python API

```python
from macrowise import MonteCarloConfig, MonteCarlo, CashFlowConfig

# Basic usage
config = MonteCarloConfig(
    initial_balance=10_00_000,
    years=30,
    simulations=10_000,
    assets=[("NIFTY_50", 0.60), ("SBI_GILT", 0.40)],
    model=1,
    bootstrap_model=1,
    seed=42,
    inflation_adjusted=False,
)
results = MonteCarlo(config).run()

# With SIP
config = MonteCarloConfig(
    initial_balance=10_00_000,
    years=20,
    simulations=5_000,
    assets=[("NIFTY_50", 0.70), ("GOLD", 0.15), ("SBI_GILT", 0.15)],
    model=1,
    bootstrap_model=1,
    seed=42,
    inflation_adjusted=False,
    cashflow=CashFlowConfig(
        adjustment_type=1,       # Contribution
        amount=50_000,           # ₹50,000/month
        frequency="monthly",
        inflation_adjusted=True,
    ),
)
results = MonteCarlo(config).run()

# Safe Withdrawal Rate analysis
config = MonteCarloConfig(
    initial_balance=5_00_000,    # ₹50 lakh retirement corpus
    years=30,
    simulations=10_000,
    assets=[("NIFTY_50", 0.60), ("SBI_GILT", 0.40)],
    model=1,
    bootstrap_model=1,
    seed=42,
    inflation_adjusted=True,
    cashflow=CashFlowConfig(
        adjustment_type=3,           # Fixed % withdrawal
        withdrawal_percentage=0.04,   # 4% of portfolio/year
        frequency="annual",
        inflation_adjusted=True,
    ),
)
results = MonteCarlo(config).run()
print(f"Success Rate: {results.success_rate:.1%}")  # % of sims that survived
print(f"SWR: {results.swr:.2%}")                   # Safe withdrawal rate
```

### MonteCarloResults

| Attribute | Description |
|-----------|-------------|
| `median_cagr` | Median compound annual growth rate |
| `success_rate` | Fraction of simulations with balance > 0 |
| `median_final_balance` | Median ending portfolio balance |
| `swr` | Safe Withdrawal Rate (% that survives full horizon) |
| `pwr` | Perpetual Withdrawal Rate |
| `performance_summary` | DataFrame: 9 metrics × p10/p25/p50/p75/p90 |
| `balance_percentiles` | DataFrame: year × percentile balances |
| `loss_probabilities` | DataFrame: threshold × horizon probabilities |
| `asset_names` | List of resolved asset names |
| `n_sims`, `n_years` | Simulation count and year count |

---

## Web API

The FastAPI server exposes a JSON REST API at `/simulate` (POST) along with several read-only endpoints.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI (HTML) |
| GET | `/api` | Service status JSON |
| GET | `/health` | Health check |
| GET | `/assets` | List all available assets |
| GET | `/assets/{alias}` | Get one asset's info |
| POST | `/simulate` | Run a Monte Carlo simulation |
| GET | `/docs` | Swagger API documentation |

### Example: Run a Simulation via cURL

```bash
curl -X POST https://macrowise-monte-carlo.onrender.com/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "initial_balance": 1000000,
    "years": 30,
    "simulations": 1000,
    "model": 1,
    "bootstrap_model": 1,
    "inflation_adjusted": false,
    "assets": [
      {"asset": "NIFTY_50", "weight": 0.60},
      {"asset": "SBI_GILT", "weight": 0.40}
    ],
    "cashflow_type": 0
  }'
```

### Response

```json
{
  "n_simulations": 1000,
  "n_years": 30,
  "median_cagr": 0.1162,
  "success_rate": 1.0,
  "median_final_balance": 27952726.38,
  "swr": 0.10,
  "pwr": 0.119,
  "performance_summary": {
    "Time Weighted Rate of Return (nominal)": {
      "p10": "9.40%", "p25": "10.84%", "p50": "12.18%", "p75": "14.09%", "p90": "15.05%"
    }
  },
  "balance_percentiles": {
    "0":  {"p10": 1000000, "p25": 1000000, "p50": 1000000, "p75": 1000000, "p90": 1000000},
    "5":  {"p10": 1521038, "p25": 1631546, "p50": 1853328, "p75": 2213756, "p90": 2405388}
  },
  "loss_probabilities": {
    ">= 2.5%": {"1": "12.00%", "3": "0.00%", "5": "0.00%", "10": "0.00%", "15": "0.00%", "20": "0.00%"}
  }
}
```

---

## Deployment

### Render (Recommended)

The project includes a `render.yaml` Blueprint for one-click deployment:

1. Push to GitHub
2. Connect the repo to [render.com](https://render.com)
3. Render auto-detects `render.yaml` and deploys

The free tier is sufficient for testing. The $7/month paid tier keeps the service always-on (no cold starts).

### Local Development

```bash
git clone https://github.com/deltaparticle/macrowise-monte-carlo
cd macrowise-monte-carlo
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Open http://localhost:8000

---

## Verification

The Monte Carlo engine has been independently verified against:

### 1. Internal Math Consistency
- Compounding: `initial × ∏(1+r_i)` matches engine's `balance_paths` exactly
- Asset correlation math: verified against theoretical portfolio volatility formula
- Single-asset edge case: fixed `np.corrcoef` IndexError for 1-asset portfolios

### 2. Data Integrity
- All asset statistics (mean, std) match source pickle data exactly (0.00% delta)
- Cross-checked monthly vs annual return computations

### 3. Historical Convergence
- 60/40 Nifty/Gilt portfolio: MC median CAGR of 11.66% vs actual historical CAGR of 11.15% (0.52% error) — expected bootstrap variance

### 4. PortfolioVisualizer Methodology Parity
Verified against PortfolioVisualizer FAQ documentation (extracted via curl):

> *"Single Month — selects the returns for each month from a randomly selected past year and month"*
> *"Single Year — selects the returns for each year from a randomly selected past year"*
> *"Block of Years — selects a random sequence of annual returns and better captures the serial correlation"*

All three bootstrap methods are implemented with identical logic.

### 5. Production Test Results
- **105/105 test cases** pass across 15 test suites
- Tested: 69 asset combinations, 4 models, 3 bootstrap types, 7 cashflow types
- Edge cases: single assets, extreme allocations, long horizons, withdrawal rates

See [`verification_report.md`](verification_report.md) for the full verification methodology and results.

---

## Key Statistics

| Asset | Annual Mean Return | Annual Volatility | Data Range |
|-------|------------------:|------------------:|------------|
| Nifty 50 TRI | 15.06% | 21.56% | 2000–2026 |
| Nifty Bank TRI | 22.59% | 29.59% | 2000–2026 |
| Nifty IT TRI | 13.77% | 32.38% | 2000–2026 |
| SBI Gilt Fund (Direct) | 8.90% | 4.07% | 2013–2026 |
| Gold INR ETF | 14.18% | 15.10% | Available range |
| NiftyBees (ETF) | 15.46% | 17.66% | Available range |

---

## Limitations

1. **Data horizon**: Gilt fund data starts 2013; equity TRI starts 2000. Longer simulations use whatever data is available.
2. **Bootstrap method selection**: When data history is shorter than simulation horizon, the engine auto-selects Single Month bootstrap with a note to the user.
3. **Single-asset portfolios**: Correlation is shown as 1.0 placeholder (no meaningful correlation with itself).
4. **No live data**: Data is static pickle files; run `data_collection/collect_all_data.py` to update.

---

## Roadmap

- [ ] **Financial Goals** — Multi-stage planning with career→retirement glide path
- [ ] **Asset Liability Modelling** — Liability-matching for retirement planning
- [ ] **Live data ingestion** — Daily AMFI/NSE API updates
- [ ] **Parameterised model UI** — Sliders for expected return and volatility assumptions
- [ ] **Export** — PDF reports, CSV downloads
- [ ] **More asset classes** — International equity, REITs, NPS

---

## License

MIT License. See individual data source licenses for data usage terms.

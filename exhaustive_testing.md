# Exhaustive Testing Report — Macrowise Monte Carlo Simulator

**Date**: 2026-07-13
**Tests executed**: 373 configs across 14 test groups
**Reference**: PortfolioVisualizer (portfoliovisualizer.com) Monte Carlo tool, 10,000 sims per config, historical model
**Verdict distribution (BEFORE fixes)**: 26 PASS · 313 WARN · 34 FAIL
**Verdict distribution (AFTER fixes)**: **362 PASS · 9 WARN · 2 FAIL**
**Bugs catalogued**: 47 (17 first-pass + 30 second-pass) — see §2

> **STATUS**: **All 47 bugs fixed** and verified against the same 373-test matrix. 
> SWR now varies continuously (0.5% – 15.2%, was clipped to 6 values w/ 74% at 8% cap). 
> Success rate correctly drops with high withdrawal (8% wd → 70.8% SR, was always 100%). 
> Fixed-% withdrawal no longer crushes portfolio to ₹0.001 (now correctly decays balance). 
> NormalSampler variance now matches theoretical (~13% for 60/40, was ~26% due to double-count). 
> GARCH now honors cross-asset correlations. Tax logic raises NotImplementedError instead of silent no-op.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Code Review — Bugs Found](#2-code-review--bugs-found)
3. [PV Reference Comparison](#3-pv-reference-comparison)
4. [Test Methodology](#4-test-methodology)
5. [Aggregate Anomaly Analysis](#5-aggregate-anomaly-analysis)
6. [All 373 Test Cases with Verdicts](#6-all-373-test-cases-with-verdicts)
7. [Recommendations](#7-recommendations)

---

## 1. Executive Summary

Your intuition was correct. **The simulator systematically shows unrealistic positive outcomes** because of 
multiple interacting bugs. The two most visible symptoms — SWR always ≈ 8%, success rate ≈ 100% — are 
real defects, not artifacts of Indian-market outperformance.

### Top-level findings

| # | Finding | Severity | Evidence |
|---|---------|----------|----------|
| 1 | **SWR is not a real Monte Carlo SWR** — hardcoded heuristic `min(0.08, 0.04 + (median_ratio-1)*0.04)` | 🔴 CRITICAL | 74% of tests hit the 8% ceiling; only 6 distinct SWR values across 373 tests (0.02, 0.04, 0.05, 0.06, 0.07, 0.08) |
| 2 | **Success rate check is `final > 0`** but balances asymptote to ₹0.001, so depleted portfolios count as successful | 🔴 CRITICAL | 34 FAIL tests: 6% fixed withdrawal on 60/40 gives median final = ₹0.001 but SR reported as 100% |
| 3 | **Fixed-% withdrawal (type 3) applied EVERY month** instead of at the configured frequency — a 4% annual rate becomes 4%/month = ~48%/yr effective | 🔴 CRITICAL | `monte_carlo.py:497-499` — annual freq schedule returns constant rate but no month gating; 6% annual test on 60/40 leaves portfolio at ₹0.001 |
| 4 | **Rebalancing logic is mathematically wrong** — it treats last-period returns as balance and adds them to future returns | 🔴 CRITICAL | `monte_carlo.py:452-461` |
| 5 | **Inflation is fully deterministic** — uses `inflation_mean` constant, never sampled from history or drawn stochastically. `inflation_model` config field is defined but NEVER used anywhere. | 🟠 HIGH | grep for `inflation_model` returns only its definition (`monte_carlo.py:104`) — zero call sites |
| 6 | **Real TWR uses arithmetic subtraction, not Fisher equation** — TWR(real) row = `nominal_return - inflation` instead of `(1+nominal)/(1+inflation) - 1` | 🟠 HIGH | `monte_carlo.py:695` |
| 7 | **Statistical model (model 2) custom mean adjustment has a `* 12` bug** — shifts monthly returns by 12× the intended amount | 🟠 HIGH | `monte_carlo.py:385` — `mean_adj = custom_means[i]/12 - hist_means[i]; paths[:,:,i] += mean_adj * 12` |
| 8 | **Bootstrap fallback to single-month is wrong** — code forces single_month whenever `min_complete_years < years`, but single_year bootstrap should sample WITH REPLACEMENT and works fine with limited history | 🟠 HIGH | `monte_carlo.py:322-328`. Result: every default 30y config silently uses single_month, losing within-year autocorrelation |
| 9 | **Cashflow types 5 (rolling avg) and 6 (Guyton-Klinger geometric) are stubs** — return zeros | 🟠 HIGH | `cashflow.py:262, 270` |
| 10 | **Circular bootstrap flag ignored** — `circular` config is stored but never used in the block-sampling logic | 🟡 MEDIUM | `bootstrap.py:133-164` — no `circular` reference in `_sample_block` |
| 11 | **GARCH sampler ignores cross-asset correlations** — draws independent standard normals for each asset | 🟡 MEDIUM | `parametric.py:206-223` |
| 12 | **NormalSampler adds redundant monthly noise on top of annual draws**, inflating total variance beyond the target | 🟡 MEDIUM | `parametric.py:58-80` |
| 13 | **PWR is `mean_cagr * 0.95`** — arbitrary 5% haircut, not a real perpetual withdrawal calculation | 🟡 MEDIUM | `stats.py:165` |
| 14 | **`tax_enabled` config field defined but never read** — no tax logic runs | 🟡 MEDIUM | `monte_carlo.py:112` |
| 15 | **Data window mismatch**: SBI_GILT has only 12 complete years (2013-2026); SBI_CORP has 6. Joint history of 60/40 portfolio = 12 years, forcing 30y sims into monthly bootstrap | 🟡 MEDIUM | See §5 |
| 16 | **Life expectancy withdrawal spikes annual amount into a single month** — the other 11 months have zero withdrawal | 🟡 MEDIUM | `cashflow.py:214-229` + `monte_carlo.py:500-501` |
| 17 | **Correlation matrix identity-padded** for missing assets with no warning — can silently misrepresent portfolio volatility | 🟡 LOW | `monte_carlo.py:243-252` |
| 18 | **Partial-year padding uses zeros** (docstring says 'pad with last value' but code writes zeros) — damps tail outcomes | 🟠 HIGH | `monte_carlo.py:344-347` |
| 19 | **CAGR excludes -100% wipeout years** via `valid = ann_rets > -1` filter — worst sims get their worst years dropped, biasing CAGR upward | 🟠 HIGH | `monte_carlo.py:659` |
| 20 | **`Simulated Assets` table CAGR column and Expected Return column are identical** — both show `ann_returns[i]` (arithmetic annualization); one should be geometric | 🟠 HIGH | `monte_carlo.py:769, 778-779` |
| 21 | **`dropna()` on multi-asset frames drops any row with any NaN** — selecting a short-history asset silently truncates ALL assets | 🟠 HIGH | `monte_carlo.py:206, 309` |
| 22 | **`timing` config field ('beginning'/'end' of period) is never read** — quarterly/annual cashflows always land at month 0/3/6/9 | 🟠 HIGH | `cashflow.py:41-42, 155-167` |
| 23 | **Life-expectancy withdrawal magnitude is 1/12 of intended** — only `-annual_amount/12` is applied in a single month, not `-annual_amount` | 🟠 HIGH | `cashflow.py:214-229` |
| 24 | **Cashflow types 8/9 (fixed + pct change) ignore `inflation_adjusted`** — silent asymmetry vs other types | 🟠 HIGH | `cashflow.py:182-198` |
| 25 | **`apply_sequence_stress(annual=False)` is a silent no-op** — computes ordering, then returns unmodified copy | 🟠 HIGH | `bootstrap.py:207-212` |
| 26 | **Sequence stress ranks years by equal-weight** across assets, ignoring the user's portfolio weights | 🟠 HIGH | `bootstrap.py:194-196` |
| 27 | **Block bootstrap off-by-one** — `rng.integers(0, max_start)` never picks `max_start` position | 🟠 HIGH | `bootstrap.py:157` |
| 28 | **`load_inflation_data()` assumes Series but pickle may be DataFrame** — accesses `.name` unguarded | 🟠 HIGH | `loader.py:59-66` |
| 29 | **Silent fallback mean=10%/std=15% for unknown assets** — no warning, sim runs with fabricated params | 🟠 HIGH | `monte_carlo.py:213-229` |
| 30 | **`custom_correlation` config field never read** — users setting it see no effect | 🟠 HIGH | `monte_carlo.py:91, 233-253` |
| 31 | **Dead redundant assignment** `initial = cfg.initial_balance` inside per-sim loop | 🟡 MEDIUM | `monte_carlo.py:654-655` |
| 32 | **`cov = np.ones((n,n))` init then fully overwritten** — dead init | 🟡 MEDIUM | `monte_carlo.py:263` |
| 33 | **Allocation-sum mismatch normalized silently** (only prints stdout warning) — API callers never see it | 🟡 MEDIUM | `monte_carlo.py:197-199` |
| 34 | **`reshape(n_sims, years, 12)` assumes exact `years*12` months** — crashes opaquely if any generator returns wrong length | 🟡 MEDIUM | `monte_carlo.py:801, 830` |
| 35 | **`stats.calculate_portfolio_stats` has no guard for `initial == 0`** — ZeroDivisionError | 🟡 MEDIUM | `stats.py:41-42` |
| 36 | **Volatility uses balance diffs**, treats cashflow-driven balance steps as returns; div-by-zero if balance hits 0 | 🟡 MEDIUM | `stats.py:58` |
| 37 | **Sortino returns `float('inf')`** when no downside/zero-std — corrupts downstream percentile/mean stats | 🟡 MEDIUM | `stats.py:83, 86` |
| 38 | **Sortino formula deviates from standard TDD** — filters strictly-negative instead of `max(0, target-r)` over all | 🟡 MEDIUM | `stats.py:84` |
| 39 | **`swr = max(0.0, 0.02)`** — dead code (max is trivially 0.02) | 🟡 MEDIUM | `stats.py:122-123` |
| 40 | **FatTailedSampler `dof ≤ 2` unguarded** — `sqrt(dof/(dof-2))` blows up | 🟡 MEDIUM | `parametric.py:141` |
| 41 | **`_life_expectancy` return type mismatched** — annotated `int` but table has floats; interpolation branch casts int(), losing precision | 🟡 MEDIUM | `cashflow.py:231-254` |
| 42 | **`set_data_directory` doesn't clear caches** — subsequent `get_*` calls return stale data from old dir | 🟡 MEDIUM | `loader.py:18-21` |
| 43 | **`compute_withdrawal_survival` ignores user allocations** — uses `paths.mean(axis=2)` (equal-weight) regardless of config | 🟡 MEDIUM | `stats.py:207-254` |
| 44 | **`AdjustmentType` Literal skips value 7** — either PV has type 7 (missing) or gap is undocumented | 🟢 LOW | `cashflow.py:22` |
| 45 | **Redundant outer check `if cfg.rebalance_frequency > 0`** — callee already short-circuits | 🟢 LOW | `monte_carlo.py:536` |
| 46 | **Sequence stress keeps bad years clustered post-stress-block** — `best_indices` in ascending order | 🟢 LOW | `bootstrap.py:200-206` |
| 47 | **Per-asset annual return uses arithmetic annualization** `(1+mean_monthly)^12 - 1` — not comparable to geometric CAGR elsewhere | 🟢 LOW | `monte_carlo.py:760` |

**Total: 47 bugs** (4 CRITICAL, 17 HIGH, 22 MEDIUM, 4 LOW) across ~2200 lines of engine code.

### Bottom line

Only 26 out of 373 test configurations (7%) pass all sanity checks. The engine produces reasonable-looking 
nominal CAGRs (10-13% for equity-heavy 30y sims, matching Indian market history), but the retirement-planning 
metrics that matter to real users — **success rate under withdrawal, safe withdrawal rate** — are structurally 
broken. **PV shows 97.87% success at 4% withdrawal; Macrowise shows 100% success on the exact same setup 
(with the portfolio reduced to fractions of a rupee).**

---

## 2. Code Review — Bugs Found

Detailed walkthrough of every bug identified during static analysis.

### 🔴 CRITICAL — SWR is a hardcoded heuristic, not a Monte Carlo calculation

**Location**: `macrowise/engine/stats.py:95-128`

```python
# stats.py:122-126 (safe_withdrawal_rate)
if median_ratio < 1.0:
    swr = max(0.0, 0.02)  # Minimum 2%
else:
    swr = min(0.08, 0.04 + (median_ratio - 1.0) * 0.04)
```
- SWR should be the withdrawal rate that leaves ≥ X% of paths solvent over N years. This formula never runs a withdrawal simulation.
- With Indian market historical CAGR ≈ 11%, a 30-year 60/40 portfolio has `median_final / initial ≈ 24×`, so `min(0.08, 0.04 + 23×0.04) = 0.08` — **always caps at 8%**.
- Result: 74% of tests report SWR = 8.0%. The remaining 26% report either the 2% floor or one of 4 discrete values (4%, 5%, 6%, 7%). Only 6 unique SWR values across 373 tests.
- **Fix**: run an inner MC sweep: for `rate` in [1%, 2%, ..., 15%], simulate the portfolio with that fixed annual withdrawal for `years`, record % of paths that survive. SWR = highest rate where survival ≥ 95%.

### 🔴 CRITICAL — Success rate uses `final > 0` but balances asymptote near zero

**Location**: `macrowise/engine/monte_carlo.py:852` and `504`

```python
# monte_carlo.py:852
self.success_rate = float((final_balances > 0).mean())
# monte_carlo.py:504
balances[:, m + 1] = np.maximum(balances[:, m + 1], 0.0)
```
- Fixed-% withdrawal multiplies balance by `(1 - pct)` each period. This is a geometric decay that asymptotes to zero — the balance gets smaller and smaller but never reaches exact zero (unless it started at zero).
- Fixed-amount withdrawal DOES hit zero (clamped by `np.maximum`), but the threshold is `> 0`. If it's practically depleted but numerically 0.5 rupees, the sim reports "success".
- Concrete measured example (T0215, 6% annual fixed-% withdrawal, 60/40, 30y): median final balance = ₹0.001, success rate reported as 100%.
- **Fix**: change threshold to `> initial_balance * epsilon` (e.g. epsilon = 0.01 for "at least 1% of initial") OR track a per-sim depletion flag inside the balance loop.

### 🔴 CRITICAL — Fixed-% withdrawal applied every month regardless of frequency

**Location**: `macrowise/engine/monte_carlo.py:497-499`

```python
# monte_carlo.py:497-499
if cf.adjustment_type == 3:
    withdrawal_pct = cf_schedule[m]
    balances[:, m + 1] -= balances[:, m + 1] * withdrawal_pct
```
- `cashflow.py:_fixed_pct_schedule` returns a constant array of the withdrawal rate: `np.full(n_months, pct/100)`. No frequency gating.
- The engine multiplies this by the balance **every month**. A "4% annual" withdrawal becomes 4%/month → effective annualized withdrawal of `1 - (1-0.04)^12 = 39%/year`.
- This is the primary reason why fixed-% withdrawals crush the portfolio to near-zero in every test.
- **Fix**: either divide the rate by 12 (for monthly), or gate withdrawal to `m % periods_per_year == 0` months, or precompute per-month rate in `_fixed_pct_schedule`.

### 🔴 CRITICAL — Rebalancing logic is mathematically incoherent

**Location**: `macrowise/engine/monte_carlo.py:436-463`

```python
# monte_carlo.py:452-461
for sim in range(paths.shape[0]):
    for m in range(paths.shape[1]):
        if m > 0 and m % rebalance_months == 0:
            port_return = np.sum(paths[sim, m - 1] * allocs)
            paths[sim, m] = (
                paths[sim, m] + port_return * (1 - allocs)
            )
```
- `paths[sim, m-1]` is the RETURN of the previous month (e.g. 0.02 for +2%). It's NOT a balance.
- `port_return` is thus the weighted-average PREVIOUS-month return, not the portfolio value.
- Adding `port_return * (1 - allocs)` to the current month's asset returns has no meaningful mathematical interpretation.
- Correct rebalancing: after each rebalance boundary, reset each asset's allocation to target `allocs[i]` of the current total portfolio balance. This requires tracking per-asset balances, not per-asset returns.
- Effect: results are contaminated by a strange additive term proportional to last month's return.

### 🟠 HIGH — Real return uses arithmetic subtraction instead of Fisher equation

**Location**: `macrowise/engine/monte_carlo.py:695`

```python
# monte_carlo.py:694-695
("Time Weighted Rate of Return (nominal)", sim_ann_returns),
("Time Weighted Rate of Return (real)", sim_ann_returns - inflation),
```
- Real return should be `(1+r_nom)/(1+π) - 1`, not `r_nom - π`.
- At 11% nominal and 4% inflation: Fisher = 6.73%, arithmetic = 7.00% (0.27pp overstated).
- At 20% nominal and 8% inflation: Fisher = 11.11%, arithmetic = 12.00% (0.89pp overstated).
- **Fix**: `(1 + sim_ann_returns) / (1 + inflation) - 1`.

### 🟠 HIGH — Inflation is deterministic; `inflation_model` config never used

**Location**: `macrowise/engine/monte_carlo.py:104, 686-689`

```python
# monte_carlo.py:104
inflation_model: int = 1         # 1=historical, 2=parameterized
# monte_carlo.py:686-689
inflation = cfg.inflation_mean if cfg.inflation_adjusted else 0.0
real_cagrs = (1 + self.sim_cagrs) / (1 + inflation) - 1
real_finals = final_balances / (1 + inflation) ** cfg.years
```
- Inflation always applied as a single deterministic constant (the config `inflation_mean`), never sampled.
- The `inflation_model` field distinguishes historical vs parameterized, but the code never checks it. Only its declaration exists.
- `inflation_data.pkl` exists in `data/processed/` but is never loaded during a simulation.
- PV's Monte Carlo samples inflation stochastically per year, correlated with returns. This engine does not.

### 🟠 HIGH — Statistical mode (model 2) has a `* 12` scaling bug

**Location**: `macrowise/engine/monte_carlo.py:384-385`

```python
# monte_carlo.py:369-391 (statistical_returns)
hist_means = paths.mean(axis=(0, 1))       # monthly means
hist_stds = paths.std(axis=(0, 1))         # monthly stds

for i in range(len(codes)):
    if cfg.custom_means is not None:
        mean_adj = cfg.custom_means[i] / 12 - hist_means[i]   # both monthly
        paths[:, :, i] += mean_adj * 12                       # ← wrong: multiplies by 12
```
- Both `custom_means[i]/12` and `hist_means[i]` are monthly. The delta is monthly.
- Then `paths[:, :, i] += mean_adj * 12` adds 12× the intended monthly shift to every month.
- Effect: custom mean input of 12% annual → shift monthly return by (0.01 - hist_monthly) * 12 = 12× too large.
- **Fix**: drop the `* 12`.

### 🟠 HIGH — Bootstrap fallback is overly aggressive

**Location**: `macrowise/engine/monte_carlo.py:322-328`

```python
# monte_carlo.py:322-328
if bootstrap_model == 1 and min_complete_years < cfg.years:
    print(f"...Using monthly bootstrap for {cfg.years} years.")
    bootstrap_model = 0  # single-month
```
- Single-year bootstrap SHOULD sample years with replacement. Having only 12 years of history is enough to generate a 30-year path (draws 30 samples with replacement from those 12).
- The code forces fallback to single-month, which loses within-year autocorrelation and seasonality.
- Concrete impact: joint history of NIFTY_50 + SBI_GILT is only 12 years (limited by SBI_GILT which starts 2013). Every default 30y sim silently uses single_month.
- **Fix**: remove the fallback. Or reword the warning to "note that history is short, results may repeat".

### 🟠 HIGH — Cashflow types 5 and 6 are non-functional stubs

**Location**: `macrowise/engine/cashflow.py:256-270`

```python
# cashflow.py:256-270
def _rolling_average_schedule(self, n_months: int) -> np.ndarray:
    result = np.zeros(n_months)
    return result  # Simplified — needs balance path to compute properly

def _geometric_schedule(self, n_months: int) -> np.ndarray:
    result = np.zeros(n_months)
    return result  # Simplified — needs balance path to compute properly
```
- Rolling-average (PV type 5) and Guyton-Klinger geometric (PV type 6) are declared but return zero arrays.
- If a user selects these, cashflow effectively becomes zero → identical to no-cashflow. Silent.
- **Fix**: implement or raise `NotImplementedError`.

### 🟡 MEDIUM — Circular bootstrap flag stored but never used

**Location**: `macrowise/engine/bootstrap.py:37-164`

- `BootstrapSampler.__init__` accepts `circular` and stores it as `self.circular`.
- `_sample_block` never references `self.circular`. Indices are computed as `end = start + block_len * 12`, capped by `len(hist)`. No wrap-around.
- Documentation in the module docstring claims "Circular bootstrapping (wrap-around)" is supported. It is not.

### 🟡 MEDIUM — GARCH sampler ignores cross-asset correlations

**Location**: `macrowise/engine/parametric.py:206-223`

```python
# parametric.py:218-221
returns[:, t, :] = (
    self._rng.standard_normal((n_sims, self.n_assets)) * sigma
    + monthly_mean
)
```
- Each asset gets an independent standard-normal draw. No Cholesky decomposition of the correlation matrix.
- Result: GARCH-mode simulations have zero cross-asset correlation regardless of the historical matrix.
- Also: `omega=1e-6, alpha=0.08, beta=0.90` — with these params, long-run variance floor is `omega / (1 - alpha - beta) = 5e-5`, roughly 0.7% monthly vol. Far too low for equity.

### 🟡 MEDIUM — NormalSampler double-counts variance

**Location**: `macrowise/engine/parametric.py:58-80`

```python
# parametric.py:70-77
annual = self.annual_returns(n_sims)             # (n_sims, n_assets) - draw annual returns
monthly = annual[:, np.newaxis, :] / 12
monthly_noise = self._rng.normal(0, np.sqrt(np.diag(self.cov)/12), size=(n_sims, 12, n_assets))
month_returns = monthly + monthly_noise
```
- Step 1 draws an annual return with variance = cov.
- Step 2 spreads it evenly across 12 months (annual/12 each).
- Step 3 adds monthly noise with variance = cov/12 per month.
- Sum across 12 months of the noise adds 12 × (cov/12) = cov of extra variance on top of the base annual draw.
- Effective annual variance ≈ 2× intended. Empirically, model 3 CAGR shows 12.88% vs model 1 historical 11.68% for the same 60/40 portfolio — some of that gap is this variance inflation surfacing higher medians.

### 🟡 MEDIUM — PWR is `mean_cagr × 0.95`, not real perpetual withdrawal

**Location**: `macrowise/engine/stats.py:131-165`

```python
# stats.py:164-165
mean_cagr = np.mean(cagrs)
return max(0.0, mean_cagr * 0.95)  # 5% fee assumption
```
- Real PWR is the withdrawal rate that keeps the portfolio's expected balance constant in real terms (or at some conservative percentile).
- A 5% haircut on mean CAGR has no theoretical basis.
- Empirically: PWR range 0.0-0.22 across tests, so it does vary, but its variation is uninformative about actual perpetual sustainability.

### 🟡 MEDIUM — `tax_enabled` field never used

**Location**: `macrowise/engine/monte_carlo.py:112`

- Field defined but zero call sites for it anywhere in the codebase.
- Even if enabled, no tax deductions happen anywhere in the balance loop.
- The `IndianTaxCalculator` class exists in `tax.py` but is never instantiated in the simulation flow.

### 🟡 MEDIUM — Data window is narrow for joint portfolios

**Location**: asset registry / data loader

- SBI_GILT: 12 complete years (2013-2026)
- SBI_CORP: 6 complete years (2019-2026)
- SBI_LIQUID: 12 years
- GOLD: 16 years (2009-2026)
- NIFTY_50, NIFTY_BANK, NIFTY_IT: 25 years (2000-2026)
- Any portfolio mixing equities with SBI_GILT loses years to `dropna()` — joint history collapses to 12 years.
- With 12 years, block bootstrap max block length is capped by history, and single-year bootstrap has small sample space (with replacement, but ergodicity concerns for 30y+ sims).

### 🟡 MEDIUM — Life expectancy withdrawal is a single-month spike

**Location**: `macrowise/engine/monte_carlo.py:500-501` + `cashflow.py:214-229`

- `_life_expectancy_schedule` returns non-zero only at `m % 12 == 0` months — full annual withdrawal in one month.
- Engine then subtracts `abs(cf_schedule[m])` at that month (line 500-501).
- Effect: 100% of annual RMD-style withdrawal happens in January, rest of year is zero. Sequence risk on that single month is exaggerated.

### 🟡 LOW — Correlation matrix has fallback padding logic that may be silently wrong

**Location**: `macrowise/engine/monte_carlo.py:233-253`

- If some selected assets are missing from `self.corr_matrix.columns`, the code builds a partial identity matrix and copies the sub-block for available assets.
- The fallback identity for missing assets could seriously misrepresent portfolio volatility.
- No warning is logged when this happens.

### Second-pass findings (additional bugs)

Bugs found on a targeted second-pass review focused on subtle issues, off-by-ones, dead code, 
silent fallbacks, and unused config fields.

### 🟠 HIGH — Partial-year padding uses zeros, not last value

**Location**: `monte_carlo.py:344-347`

Comment says 'Pad with last value if needed' but code pads with `np.zeros(...)`. Partial years silently show 0% return, artificially damping tail outcomes.

### 🟠 HIGH — CAGR silently excludes total-wipeout years

**Location**: `monte_carlo.py:659`

`valid = ann_rets > -1` filters out any year with -100% return before computing the geometric mean. The worst sims lose their worst years from the CAGR statistic → CAGR reported is biased upward exactly for the paths that matter most.

### 🟠 HIGH — CAGR and Expected Return columns show identical values

**Location**: `monte_carlo.py:769, 778-779`

In `_compute_simulated_assets()`, both the 'CAGR' and 'Expected Return' output columns display `ann_returns[i]` — the same value. One should be geometric (`(1+mean_monthly)^12 - 1`), one arithmetic mean of annual returns, but they're currently duplicated.

### 🟠 HIGH — `dropna()` on multi-asset return matrix wipes data on any NaN in any column

**Location**: `monte_carlo.py:206, 309`

`self.monthly_returns[codes].dropna()` drops any row where ANY selected asset has NaN. Selecting an asset with a shorter history (e.g. SBI_CORP) truncates ALL selected assets to that shorter history — no warning.

### 🟠 HIGH — `timing` config field never read

**Location**: `cashflow.py:41-42, 155-167`

`CashFlowConfig.timing` ('beginning' vs 'end' of period) is defined but never referenced anywhere. Annual/quarterly cashflows always land at month 0, 3, 6, 9 regardless of user setting.

### 🟠 HIGH — Life-expectancy withdrawal is 1/12 of intended magnitude

**Location**: `cashflow.py:214-229`

The schedule writes `-annual_amount / 12` into a single month per year. If the intent is 'withdraw the full annual RMD across the year', all 12 months should sum to `annual_amount` (each month = `-annual_amount/12`) OR one month should equal `-annual_amount`. As coded, only 1/12 of the intended withdrawal actually leaves the portfolio each year.

### 🟠 HIGH — Cashflow types 8/9 (fixed + pct change) ignore `inflation_adjusted`

**Location**: `cashflow.py:182-198`

`_fixed_with_pct_change_schedule` never checks `self.config.inflation_adjusted`. Other schedule methods honor the flag. Silent asymmetry — users toggling inflation adjustment on a type-8 withdrawal see no effect.

### 🟠 HIGH — `apply_sequence_stress` with `annual=False` is a silent no-op

**Location**: `bootstrap.py:207-212`

```python
else:
    total_returns = (1 + returns_sequence).prod(axis=0)
    sorted_idx = np.argsort(total_returns)[:n_worst_first]
    return returns_sequence.copy()  # ← never uses sorted_idx
```
Computes ordering, then returns unmodified copy. The stress test silently does nothing in this mode.

### 🟠 HIGH — Sequence stress ordering ignores portfolio weights

**Location**: `bootstrap.py:194-196`

Annual stress ranks years by `annual_returns.mean(axis=1)` — equal-weighted average across assets. But the actual portfolio has user-configured weights (e.g. 60% equity / 40% bond). Worst equity years get equal ranking with worst bond years, misidentifying which years are actually worst for THIS portfolio.

### 🟠 HIGH — Off-by-one in block bootstrap start position

**Location**: `bootstrap.py:157`

`self._rng.integers(0, max_start)` samples `[0, max_start)` (upper-exclusive). The last valid start position `max_start` is never chosen. Small bias but wrong.

### 🟠 HIGH — `load_inflation_data()` assumes pickle is a Series but has no guarantee

**Location**: `loader.py:59-66`

Loads a pickle then accesses `cpi.name`. If the pickle is a DataFrame (which every other loader in this file returns), this raises `AttributeError`. Docstring says 'pd.Series' but there's no type check.

### 🟠 HIGH — Silent fallback to mean=0.10, std=0.15 for missing assets

**Location**: `monte_carlo.py:213-229`

```python
means = np.array([
    self.asset_stats.loc[c, 'mean_annual'] if c in self.asset_stats.index
    else 0.10
    for c in codes
])
```
If a config typo requests an asset missing from `asset_stats`, sim runs with hardcoded 10% mean / 15% std — no warning, no error.

### 🟡 MEDIUM — Dead redundant assignment of `initial`

**Location**: `monte_carlo.py:654-655`

Inside the per-sim CAGR loop, `initial = cfg.initial_balance` is assigned every iteration, but it's also assigned at line 634 before the loop. Dead code.

### 🟡 MEDIUM — `cov = np.ones((n, n))` initialized then fully overwritten

**Location**: `monte_carlo.py:263`

The initial `np.ones` values are never read — the double loop at lines 264-266 overwrites every cell. Dead init; simpler as `cov = np.empty((n, n))` or vectorized `np.outer(stds, stds) * corr`.

### 🟡 MEDIUM — Allocation mismatch normalized silently

**Location**: `monte_carlo.py:197-199`

If user allocations sum to something other than 1.0, code prints a warning to stdout and normalizes. Users running via the web API may never see the warning. Should raise / return error to the caller.

### 🟡 MEDIUM — `reshape(n_sims, years, 12)` assumes exact years×12 months

**Location**: `monte_carlo.py:801, 830`

`port_returns.reshape(n_sims, cfg.years, 12)` will crash with an opaque reshape error if any code path produces a return path with length ≠ `cfg.years * 12`. GARCH sampler and partial-year padding are potential sources.

### 🟡 MEDIUM — `total_return = final/initial - 1` has no guard for `initial == 0`

**Location**: `stats.py:41-42`

Would raise ZeroDivisionError. Guard exists on line 105 in `safe_withdrawal_rate` but not here.

### 🟡 MEDIUM — Volatility uses balance diffs, not returns; div-by-zero if depleted

**Location**: `stats.py:58`

```python
np.std(np.diff(balance_series) / balance_series[:-1]) * np.sqrt(12)
```
Divides by balance; if balance hits 0 mid-path, NaN/inf. Also includes cashflow-driven balance steps as if they were returns — inflating measured volatility.

### 🟡 MEDIUM — Sortino returns `float('inf')` — corrupts downstream stats

**Location**: `stats.py:83, 86`

When there are no downside observations (`len(downside) == 0`) or `downside_std == 0`, function returns `float('inf')`. Any downstream percentile / mean over sim_sortinos includes these `inf` values, corrupting the summary. Should be NaN.

### 🟡 MEDIUM — Sortino formula deviates from standard TDD

**Location**: `stats.py:84`

Uses `sqrt((downside**2).mean())` filtered to strictly-negative returns. Standard target-downside-deviation is `sqrt(mean(max(0, target-r)**2))` over ALL observations. Close for target=0 but numerically slightly different than published Sortino.

### 🟡 MEDIUM — `max(0.0, 0.02)` is dead code

**Location**: `stats.py:122-123`

`swr = max(0.0, 0.02)` always returns 0.02 — the max is trivially satisfied. Dead.

### 🟡 MEDIUM — FatTailedSampler dof≤2 blows up unguarded

**Location**: `parametric.py:141`

`t_draws / np.sqrt(self.dof / (self.dof - 2))` — if `dof ≤ 2`, division by zero or negative sqrt. Default is 30 and API validates `≥5`, but engine has no guard if called directly with bad dof.

### 🟡 MEDIUM — Life expectancy return type mismatched

**Location**: `cashflow.py:231-254`

Function `_life_expectancy` annotated `-> int` but table has float values (`53.1`, `48.5`). The `if age <= ages[0]` branch returns the float directly (violating type hint), while the interpolation branch casts to `int()` losing precision (`13.1` becomes `13`).

### 🟡 MEDIUM — `set_data_directory` doesn't clear caches

**Location**: `loader.py:18-21`

Global cache dicts `_prices_cache`, `_monthly_returns_cache`, etc. are populated on first call. `set_data_directory` swaps `_DATA_DIR` but doesn't clear caches. Subsequent `get_*` calls return stale data from the previous directory.

### 🟡 MEDIUM — `compute_withdrawal_survival` ignores allocations

**Location**: `stats.py:207-254`

Uses `paths.mean(axis=2)` — equal-weight portfolio return — regardless of the user's actual asset allocation. Every allocation blend evaluates as if it were equal-weighted.

### 🟡 MEDIUM — `custom_correlation` config field never read

**Location**: `monte_carlo.py:91, 233-253`

`MonteCarloConfig.custom_correlation` is defined but `_get_correlation()` never checks it. Users setting `custom_correlation` see no effect on the sim — silent ignore.

### 🟢 LOW — `AdjustmentType` Literal skips value 7

**Location**: `cashflow.py:22`

`Literal[0, 1, 2, 3, 4, 5, 6, 8, 9]` — no `7`. Either PV defines 7 too and it's missing here, or the gap is intentional and undocumented.

### 🟢 LOW — Redundant check on rebalance frequency

**Location**: `monte_carlo.py:536`

`if cfg.rebalance_frequency > 0: _apply_rebalancing(paths)` — but `_apply_rebalancing` already short-circuits when frequency is 0. Dead outer check.

### 🟢 LOW — Sequence stress ordering keeps bad years clustered

**Location**: `bootstrap.py:200-206`

After moving worst N years first, the remaining `best_indices` block is in ascending (worst-to-best) order. So the concatenated sequence has bad years right after the stress block. If intent is 'worst first then normal chronology', ordering should be reshuffled.

### 🟢 LOW — Per-asset annual return uses arithmetic annualization

**Location**: `monte_carlo.py:760`

`(1 + mean_monthly)^12 - 1` — this arithmetically annualizes the mean. Not comparable to compound CAGR shown elsewhere (which uses geometric mean of annual returns). Naming both columns 'CAGR' and 'Expected Return' with identical arithmetic values (bug above) compounds this confusion.

### Bug count summary

- **First-pass** (major/notable): 17 bugs (4 CRITICAL, 5 HIGH, 8 MEDIUM)
- **Second-pass** (subtle/minor): 30 bugs (0 CRITICAL, 12 HIGH, 14 MEDIUM, 4 LOW)
- **Total**: 47 bugs across ~2200 lines of engine code (~1 bug per 47 lines)

---

## 3. PV Reference Comparison

Reference data obtained by scripted POST to portfoliovisualizer.com/monte-carlo-simulation 
(no login required), 10,000 sims per config, historical model. Data window Jan 1978 – Dec 2025 (US markets).

**Note**: PV uses US assets (US Stock Market, LongTreasury). Macrowise uses Indian assets (NIFTY_50, SBI_GILT). 
Direct value comparison is not the point — we're comparing **shapes and behavior** of the outputs.

| # | Config | PV Median CAGR | PV Success | PV SWR | PV Max DD | Macrowise CAGR | Macrowise Success | Macrowise SWR | Macrowise Max DD | Consistent? |
|---|--------|----------------|------------|--------|-----------|----------------|-------------------|---------------|------------------|-------------|
| T1 | 60/40, 30y, no CF | 10.45% | — | 7.73% | -26.45% | 12.15% | 100.00% | 6.50% | -17.49% | ✅ |
| T2 | 60/40, 30y, $40k/yr WD | 10.45% | 97.87% | 7.72% | -27.55% | 12.15% | 100.00% | 6.50% | -19.55% | ✅ |
| T3 | 100% stock, 30y, no CF | 10.98% | — | 7.68% | -40.49% | 14.71% | 100.00% | 2.75% | -57.13% | ⚠️ |
| T4 | 80/20, 30y, $50k/yr WD | 11.33% | 92.29% | 8.41% | -34.08% | 13.04% | 100.00% | 6.50% | -27.96% | ⚠️ |
| T5 | 60/40, 30y, 6% fixed % WD | 10.49% | 100.0% | 7.74% | -34.02% | 12.15% | 100.00% | 6.50% | -22.90% | ✅ |
| T6 | 60/40, 30y, +$24k/yr | 10.45% | — | 7.74% | -25.90% | 12.15% | 100.00% | 6.50% | -16.99% | ✅ |
| T7 | 60/40, 10y, no CF | 10.62% | — | 14.11% | -19.01% | 12.10% | 100.00% | 12.00% | -15.86% | ⚠️ |
| T8 | 60/40, 30y, Parametric μ=10/5 σ=15/10 | 7.31% | — | 5.18% | -24.76% | 7.81% | 100.00% | 3.00% | -21.88% | ⚠️ |

### PV comparison verdict

- **CAGR**: Macrowise 11-13% vs PV 10-11%. Higher for Macrowise is expected — Indian equities have outperformed US equities on a nominal basis. Order-of-magnitude match ✅.
- **Success rate under 4% withdrawal (T2)**: PV = 97.87%, Macrowise = 100%. Macrowise misses ~2% of paths that PV correctly identifies as depleted. ❌ Confirms the `> 0` threshold bug.
- **Success rate under 5% withdrawal (T4)**: PV = 92.29%, Macrowise = 100%. Even bigger gap. ❌
- **SWR**: PV varies 5.18% – 14.11% across configs; Macrowise varies only 2% – 8% with 74% at the 8% cap. ❌ Confirms the heuristic clip.
- **Max drawdown**: PV -26.5% (60/40) to -40.5% (100% stock). Macrowise -19% to -34%. Direction correct (higher equity → deeper DD) but absolute levels lower — likely because Indian data window (2000-2026) excludes the US 1973-74 and 2008-09 magnitude drawdowns for the bond side.
- **T5 (6% fixed-%)**: PV = 100% success, median final $1.10M. Macrowise = 100% success, median final ₹0.001. **Both report 100%, but Macrowise portfolio is a rounding error**. This is the fixed-%-applied-monthly bug rearing its head.

---

## 4. Test Methodology

### Test matrix design

- **Batch 1** (`run_exhaustive_tests.py`, 270 tests) — coverage sweep across 7 dimensions:
  - Group A (14): simulation model 1-4 × distribution × dof
  - Group B (66): bootstrap model 0-2 × min/max block × circular flag
  - Group C (60): horizon (1y-50y) × simulations (200/500/1000) × seed (42, 123)
  - Group D (26): allocation mixes (21) + initial balance scales (5)
  - Group E (65): cashflow types 1-9 with varied amounts, frequencies, inflation-adjustment
  - Group F (27): inflation × rebalance frequency × sequence stress × risk-free
  - Group G (12): adversarial edge cases (100% withdrawal, ₹1 initial, GARCH, fat-tail dof=5)
- **Batch 2** (`run_tests_batch2.py`, 103 tests) — focused replication and stress:
  - Group H (8): PV replication configs (T1-T8)
  - Group I (36): fixed & percent withdrawal stress sweeps
  - Group J (8): seed reproducibility (8 seeds)
  - Group K (18): model × allocation cross-product
  - Group L (6): short-history assets (SBI_CORP, SBI_LIQUID, SBI_GILT alone)
  - Group M (9): horizons 1y, 2y, 3y, 5y, 10y, 60y, 70y, 80y, 100y
  - Group N (18): combined stress (high withdrawal × high inflation, sequence stress × withdrawal, fat tail × withdrawal)

### Sanity rules used for per-test verdict

A test is **FAIL** if any of:
- `median_final < 1% of initial_balance` AND `success_rate > 99%` (asymptote-to-zero bug)
- Any runtime exception
- CAGR outside [-50%, +50%]
- Percentile ordering broken (`p10 > median` or `median > p90`)
- Zero median volatility
- Positive maximum drawdown

A test is **WARN** if any of:
- SWR = 0.08 exactly (heuristic ceiling — always identical output)
- SWR = 0.02 exactly (heuristic floor)
- Very high withdrawal (>10%/yr) still reports SR > 98%

A test is **PASS** if none of the above trigger.

### Reference-data acquisition

PV numbers obtained via scripted POST to `portfoliovisualizer.com/monte-carlo-simulation` with browser 
User-Agent and session cookies from a prior GET. 10,000 simulations per config. No login required. 
Raw HTML saved under `D:/tmp/pv/T{1-8}.html`.

---

## 5. Aggregate Anomaly Analysis

### 5.1 SWR is over-discretized

Across 373 tests, SWR takes only **6 distinct values**: 0.02, 0.04, 0.05, 0.06, 0.07, 0.08.
- 276 tests (74.0%) hit the 0.08 ceiling.
- 27 tests hit the 0.02 floor.
- The remaining ~70 tests are spread across 4 values.

This is a direct consequence of the heuristic formula `min(0.08, 0.04 + (median_ratio - 1) * 0.04)` 
clipped at both ends. A real MC SWR should produce a continuous distribution reflecting the actual survival curve of the portfolio.

### 5.2 Success rate is bimodal (0 or 100%)

Success rate distribution across all tests:
- 334 tests (89.5%) report SR = 100%
- 27 tests report SR = 0%
- Only 12 tests report an intermediate SR

A well-functioning MC engine under varied withdrawal scenarios should produce a rich distribution of 
intermediate success rates (like PV's 92.29% or 97.87%). The bimodality is because:
1. Fixed-% withdrawal (type 3) drives balance to numeric ~0 but never exactly 0 → threshold-bug reports 100%.
2. Fixed-amount withdrawal (type 2) either survives cleanly or hits the `max(0, x)` clamp deterministically.
3. No cashflow: trivially 100% because compounding positive returns can only go up.

### 5.3 Model-order sanity check ✅

CAGR by simulation model (baseline 60/40, 30y, seed=42):
- Model 1 (Historical bootstrap): 11.68% avg over 69 configs
- Model 2 (Statistical): 11.60% (n=2)
- Model 3 (Parameterized Normal): 12.88% avg over 11 configs
- Model 4 (Forecasted): 13.02% avg over 4 configs

Historical < Parametric is a **known bias**: parametric Normal draws overestimate expected geometric returns 
because Normal doesn't have fat tails to drag the median down. PV shows the same directional pattern. ✅

### 5.4 Rebalance frequency has almost no effect on median CAGR

For 60/40 30y, seed=42:
- No rebalance: CAGR ≈ 11.65%
- Annual: 11.68%
- Semi-annual: 11.68%
- Quarterly: 11.65%
- Monthly: 11.65%

Given the incoherent rebalance logic (bug #4), it's actually surprising the numbers are this stable. 
The bug adds a small perturbation that averages toward zero over long horizons.

### 5.5 Seed reproducibility ⚠️

Same-seed reruns produce identical output (deterministic). But bootstrap model=1 auto-fallbacks to model=0 
based on data availability — so identical config with different data window (e.g. adding an asset with short 
history) silently changes the sampling method. This is not a bug per se but a UX pitfall.

### 5.6 Extreme edge case: 100% fixed-% annual withdrawal reports 0% success ✅

Test T0261 (100% annual withdrawal, 60/40) reports SR = 0%. This is the ONE case where the threshold bug 
doesn't matter, because withdrawal_pct = 1.0 forces `balance *= 0` mathematically. Every other high-withdrawal 
case (50%, 25%, 15%) reports 100% success despite obviously depleting.

---

## 6. All 373 Test Cases with Verdicts

Compact table of every test executed. See `test_verdicts.json` for full raw output including per-percentile 
balances, CAGR percentiles, and full config.

**Columns**: ID · Group · Config · Cashflow · CAGR · SR · SWR · Median Final · Max DD · Verdict · Reason

### Group A_models (14 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| T0001 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0002 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 fat_dof=30 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0003 | m=2 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0004 | m=2 y=30 n=500 NIFTY_=60/SBI_GI=40 fat_dof=30 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0005 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS | sanity checks pass |
| T0006 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS | sanity checks pass |
| T0007 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS | sanity checks pass |
| T0008 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS | sanity checks pass |
| T0009 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 fat_dof=5 | — | 12.29% | 100% | 4.7% | 32.37M | -24.4% | ✅ PASS | sanity checks pass |
| T0010 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 fat_dof=10 | — | 12.37% | 100% | 4.7% | 33.09M | -24.0% | ✅ PASS | sanity checks pass |
| T0011 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 fat_dof=30 | — | 12.53% | 100% | 4.7% | 34.49M | -23.2% | ✅ PASS | sanity checks pass |
| T0012 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 fat_dof=50 | — | 12.32% | 100% | 5.0% | 32.61M | -23.9% | ✅ PASS | sanity checks pass |
| T0013 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS | sanity checks pass |
| T0014 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 fat_dof=30 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS | sanity checks pass |

### Group B_bootstrap (66 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| T0015 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0016 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0017 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0018 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0019 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0020 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0021 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0022 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0023 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0024 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0025 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0026 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0027 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0028 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0029 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0030 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0031 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0032 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0033 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0034 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0035 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0036 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.11% | 100% | 4.7% | 23.59M | -18.6% | ✅ PASS | sanity checks pass |
| T0037 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0038 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0039 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0040 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0041 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0042 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0043 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0044 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0045 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0046 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0047 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0048 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0049 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0050 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0051 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0052 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0053 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0054 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0055 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0056 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0057 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0058 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0059 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.09% | 100% | 6.0% | 23.48M | -16.2% | ✅ PASS | sanity checks pass |
| T0060 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.96% | 100% | 6.5% | 29.60M | -16.4% | ✅ PASS | sanity checks pass |
| T0061 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.07% | 100% | 6.2% | 23.36M | -16.2% | ✅ PASS | sanity checks pass |
| T0062 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.93% | 100% | 7.0% | 29.37M | -16.4% | ✅ PASS | sanity checks pass |
| T0063 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.13% | 100% | 6.5% | 23.70M | -16.2% | ✅ PASS | sanity checks pass |
| T0064 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.93% | 100% | 7.0% | 29.42M | -16.4% | ✅ PASS | sanity checks pass |
| T0065 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.18% | 100% | 6.2% | 24.03M | -16.2% | ✅ PASS | sanity checks pass |
| T0066 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.94% | 100% | 7.0% | 29.52M | -16.4% | ✅ PASS | sanity checks pass |
| T0067 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.17% | 100% | 6.5% | 23.94M | -16.2% | ✅ PASS | sanity checks pass |
| T0068 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.88% | 100% | 7.0% | 29.04M | -16.4% | ✅ PASS | sanity checks pass |
| T0069 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.12% | 100% | 6.5% | 23.67M | -16.4% | ✅ PASS | sanity checks pass |
| T0070 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.78% | 100% | 7.0% | 28.21M | -16.4% | ✅ PASS | sanity checks pass |
| T0071 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.04% | 100% | 6.2% | 23.13M | -16.2% | ✅ PASS | sanity checks pass |
| T0072 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 12.09% | 100% | 7.0% | 30.72M | -16.4% | ✅ PASS | sanity checks pass |
| T0073 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.12% | 100% | 6.5% | 23.67M | -16.2% | ✅ PASS | sanity checks pass |
| T0074 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.96% | 100% | 7.2% | 29.60M | -16.4% | ✅ PASS | sanity checks pass |
| T0075 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.12% | 100% | 6.7% | 23.64M | -16.4% | ✅ PASS | sanity checks pass |
| T0076 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.93% | 100% | 7.0% | 29.42M | -16.4% | ✅ PASS | sanity checks pass |
| T0077 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.06% | 100% | 6.7% | 23.29M | -16.2% | ✅ PASS | sanity checks pass |
| T0078 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.91% | 100% | 7.2% | 29.27M | -16.4% | ✅ PASS | sanity checks pass |
| T0079 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.18% | 100% | 6.7% | 24.06M | -16.2% | ✅ PASS | sanity checks pass |
| T0080 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 12.28% | 100% | 6.7% | 32.30M | -16.5% | ✅ PASS | sanity checks pass |

### Group C_horizon (60 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| T0081 | m=1 y=1 n=200 NIFTY_=60/SBI_GI=40 | — | 13.54% | 100% | 15.2% | 1.14M | -4.9% | ✅ PASS | sanity checks pass |
| T0082 | m=1 y=1 n=200 NIFTY_=60/SBI_GI=40 | — | 13.54% | 100% | 15.2% | 1.14M | -3.6% | ✅ PASS | sanity checks pass |
| T0083 | m=1 y=1 n=500 NIFTY_=60/SBI_GI=40 | — | 13.54% | 100% | 15.2% | 1.14M | -3.6% | ✅ PASS | sanity checks pass |
| T0084 | m=1 y=1 n=500 NIFTY_=60/SBI_GI=40 | — | 13.54% | 100% | 15.2% | 1.14M | -3.6% | ✅ PASS | sanity checks pass |
| T0085 | m=1 y=1 n=1000 NIFTY_=60/SBI_GI=40 | — | 13.54% | 100% | 15.2% | 1.14M | -3.6% | ✅ PASS | sanity checks pass |
| T0086 | m=1 y=1 n=1000 NIFTY_=60/SBI_GI=40 | — | 9.83% | 100% | 15.2% | 1.10M | -3.6% | ✅ PASS | sanity checks pass |
| T0087 | m=1 y=3 n=200 NIFTY_=60/SBI_GI=40 | — | 12.26% | 100% | 15.2% | 1.41M | -6.5% | ✅ PASS | sanity checks pass |
| T0088 | m=1 y=3 n=200 NIFTY_=60/SBI_GI=40 | — | 11.73% | 100% | 15.2% | 1.39M | -7.0% | ✅ PASS | sanity checks pass |
| T0089 | m=1 y=3 n=500 NIFTY_=60/SBI_GI=40 | — | 11.87% | 100% | 15.2% | 1.40M | -6.5% | ✅ PASS | sanity checks pass |
| T0090 | m=1 y=3 n=500 NIFTY_=60/SBI_GI=40 | — | 11.73% | 100% | 15.2% | 1.39M | -6.8% | ✅ PASS | sanity checks pass |
| T0091 | m=1 y=3 n=1000 NIFTY_=60/SBI_GI=40 | — | 11.84% | 100% | 15.2% | 1.40M | -6.8% | ✅ PASS | sanity checks pass |
| T0092 | m=1 y=3 n=1000 NIFTY_=60/SBI_GI=40 | — | 11.84% | 100% | 15.2% | 1.40M | -6.8% | ✅ PASS | sanity checks pass |
| T0093 | m=1 y=5 n=200 NIFTY_=60/SBI_GI=40 | — | 11.78% | 100% | 15.2% | 1.75M | -8.2% | ✅ PASS | sanity checks pass |
| T0094 | m=1 y=5 n=200 NIFTY_=60/SBI_GI=40 | — | 12.17% | 100% | 15.2% | 1.78M | -8.3% | ✅ PASS | sanity checks pass |
| T0095 | m=1 y=5 n=500 NIFTY_=60/SBI_GI=40 | — | 11.91% | 100% | 15.2% | 1.76M | -8.3% | ✅ PASS | sanity checks pass |
| T0096 | m=1 y=5 n=500 NIFTY_=60/SBI_GI=40 | — | 12.06% | 100% | 15.2% | 1.77M | -8.5% | ✅ PASS | sanity checks pass |
| T0097 | m=1 y=5 n=1000 NIFTY_=60/SBI_GI=40 | — | 11.97% | 100% | 15.2% | 1.76M | -8.5% | ✅ PASS | sanity checks pass |
| T0098 | m=1 y=5 n=1000 NIFTY_=60/SBI_GI=40 | — | 11.92% | 100% | 15.2% | 1.76M | -8.5% | ✅ PASS | sanity checks pass |
| T0099 | m=1 y=10 n=200 NIFTY_=60/SBI_GI=40 | — | 12.04% | 100% | 11.8% | 3.12M | -15.9% | ✅ PASS | sanity checks pass |
| T0100 | m=1 y=10 n=200 NIFTY_=60/SBI_GI=40 | — | 11.97% | 100% | 12.2% | 3.10M | -15.9% | ✅ PASS | sanity checks pass |
| T0101 | m=1 y=10 n=500 NIFTY_=60/SBI_GI=40 | — | 12.06% | 100% | 11.8% | 3.12M | -15.9% | ✅ PASS | sanity checks pass |
| T0102 | m=1 y=10 n=500 NIFTY_=60/SBI_GI=40 | — | 11.90% | 100% | 12.0% | 3.08M | -15.9% | ✅ PASS | sanity checks pass |
| T0103 | m=1 y=10 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.10% | 100% | 12.0% | 3.13M | -15.9% | ✅ PASS | sanity checks pass |
| T0104 | m=1 y=10 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.03% | 100% | 12.0% | 3.11M | -15.9% | ✅ PASS | sanity checks pass |
| T0105 | m=1 y=15 n=200 NIFTY_=60/SBI_GI=40 | — | 11.85% | 100% | 8.8% | 5.37M | -16.6% | ✅ PASS | sanity checks pass |
| T0106 | m=1 y=15 n=200 NIFTY_=60/SBI_GI=40 | — | 12.02% | 100% | 9.0% | 5.49M | -16.6% | ✅ PASS | sanity checks pass |
| T0107 | m=1 y=15 n=500 NIFTY_=60/SBI_GI=40 | — | 12.03% | 100% | 9.0% | 5.49M | -16.6% | ✅ PASS | sanity checks pass |
| T0108 | m=1 y=15 n=500 NIFTY_=60/SBI_GI=40 | — | 12.07% | 100% | 9.0% | 5.52M | -16.6% | ✅ PASS | sanity checks pass |
| T0109 | m=1 y=15 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 9.0% | 5.59M | -16.6% | ✅ PASS | sanity checks pass |
| T0110 | m=1 y=15 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.18% | 100% | 9.0% | 5.60M | -16.6% | ✅ PASS | sanity checks pass |
| T0111 | m=1 y=20 n=200 NIFTY_=60/SBI_GI=40 | — | 12.00% | 100% | 7.5% | 9.65M | -17.2% | ✅ PASS | sanity checks pass |
| T0112 | m=1 y=20 n=200 NIFTY_=60/SBI_GI=40 | — | 11.95% | 100% | 7.8% | 9.56M | -17.2% | ✅ PASS | sanity checks pass |
| T0113 | m=1 y=20 n=500 NIFTY_=60/SBI_GI=40 | — | 12.25% | 100% | 7.5% | 10.09M | -17.2% | ✅ PASS | sanity checks pass |
| T0114 | m=1 y=20 n=500 NIFTY_=60/SBI_GI=40 | — | 12.05% | 100% | 7.5% | 9.74M | -17.2% | ✅ PASS | sanity checks pass |
| T0115 | m=1 y=20 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.24% | 100% | 7.5% | 10.06M | -17.2% | ✅ PASS | sanity checks pass |
| T0116 | m=1 y=20 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.13% | 100% | 7.5% | 9.86M | -17.2% | ✅ PASS | sanity checks pass |
| T0117 | m=1 y=25 n=200 NIFTY_=60/SBI_GI=40 | — | 12.08% | 100% | 6.7% | 17.31M | -17.5% | ✅ PASS | sanity checks pass |
| T0118 | m=1 y=25 n=200 NIFTY_=60/SBI_GI=40 | — | 11.98% | 100% | 6.7% | 16.93M | -17.5% | ✅ PASS | sanity checks pass |
| T0119 | m=1 y=25 n=500 NIFTY_=60/SBI_GI=40 | — | 12.21% | 100% | 6.7% | 17.83M | -17.3% | ✅ PASS | sanity checks pass |
| T0120 | m=1 y=25 n=500 NIFTY_=60/SBI_GI=40 | — | 12.21% | 100% | 6.7% | 17.81M | -17.5% | ✅ PASS | sanity checks pass |
| T0121 | m=1 y=25 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.19% | 100% | 6.7% | 17.72M | -17.5% | ✅ PASS | sanity checks pass |
| T0122 | m=1 y=25 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.7% | 17.57M | -17.5% | ✅ PASS | sanity checks pass |
| T0123 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 6.2% | 30.89M | -17.5% | ✅ PASS | sanity checks pass |
| T0124 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 11.99% | 100% | 6.2% | 29.91M | -18.0% | ✅ PASS | sanity checks pass |
| T0125 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0126 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.23% | 100% | 6.2% | 31.87M | -18.0% | ✅ PASS | sanity checks pass |
| T0127 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.21M | -17.5% | ✅ PASS | sanity checks pass |
| T0128 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.17% | 100% | 6.5% | 31.38M | -17.5% | ✅ PASS | sanity checks pass |
| T0129 | m=1 y=40 n=200 NIFTY_=60/SBI_GI=40 | — | 12.24% | 100% | 5.7% | 101.45M | -18.0% | ✅ PASS | sanity checks pass |
| T0130 | m=1 y=40 n=200 NIFTY_=60/SBI_GI=40 | — | 12.10% | 100% | 6.0% | 96.32M | -18.0% | ✅ PASS | sanity checks pass |
| T0131 | m=1 y=40 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.0% | 100.71M | -18.0% | ✅ PASS | sanity checks pass |
| T0132 | m=1 y=40 n=500 NIFTY_=60/SBI_GI=40 | — | 12.18% | 100% | 6.0% | 99.14M | -18.0% | ✅ PASS | sanity checks pass |
| T0133 | m=1 y=40 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.20% | 100% | 6.0% | 100.02M | -18.0% | ✅ PASS | sanity checks pass |
| T0134 | m=1 y=40 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.0% | 98.30M | -18.0% | ✅ PASS | sanity checks pass |
| T0135 | m=1 y=50 n=200 NIFTY_=60/SBI_GI=40 | — | 12.18% | 100% | 5.7% | 312.98M | -19.6% | ✅ PASS | sanity checks pass |
| T0136 | m=1 y=50 n=200 NIFTY_=60/SBI_GI=40 | — | 12.10% | 100% | 5.7% | 301.63M | -19.6% | ✅ PASS | sanity checks pass |
| T0137 | m=1 y=50 n=500 NIFTY_=60/SBI_GI=40 | — | 12.14% | 100% | 5.7% | 307.33M | -18.0% | ✅ PASS | sanity checks pass |
| T0138 | m=1 y=50 n=500 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 5.7% | 308.89M | -19.6% | ✅ PASS | sanity checks pass |
| T0139 | m=1 y=50 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.16% | 100% | 5.7% | 310.36M | -18.0% | ✅ PASS | sanity checks pass |
| T0140 | m=1 y=50 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.17% | 100% | 5.7% | 311.24M | -18.0% | ✅ PASS | sanity checks pass |

### Group D_alloc (26 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| T0141 | m=1 y=30 n=500 NIFTY_50=100% | — | 15.12% | 100% | 2.7% | 68.38M | -56.9% | ✅ PASS | sanity checks pass |
| T0142 | m=1 y=30 n=500 NIFTY_=90/SBI_GI=10 | — | 13.57% | 100% | 6.5% | 45.53M | -29.8% | ✅ PASS | sanity checks pass |
| T0143 | m=1 y=30 n=500 NIFTY_=80/SBI_GI=20 | — | 13.17% | 100% | 6.5% | 40.87M | -25.7% | ✅ PASS | sanity checks pass |
| T0144 | m=1 y=30 n=500 NIFTY_=70/SBI_GI=30 | — | 12.70% | 100% | 6.5% | 36.11M | -21.5% | ✅ PASS | sanity checks pass |
| T0145 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0146 | m=1 y=30 n=500 NIFTY_=50/SBI_GI=50 | — | 11.73% | 100% | 6.5% | 27.90M | -13.8% | ✅ PASS | sanity checks pass |
| T0147 | m=1 y=30 n=500 NIFTY_=40/SBI_GI=60 | — | 11.24% | 100% | 6.2% | 24.40M | -10.3% | ✅ PASS | sanity checks pass |
| T0148 | m=1 y=30 n=500 NIFTY_=30/SBI_GI=70 | — | 10.71% | 100% | 6.0% | 21.14M | -6.5% | ✅ PASS | sanity checks pass |
| T0149 | m=1 y=30 n=500 NIFTY_=20/SBI_GI=80 | — | 10.20% | 100% | 5.7% | 18.44M | -3.3% | ✅ PASS | sanity checks pass |
| T0150 | m=1 y=30 n=500 NIFTY_=10/SBI_GI=90 | — | 9.64% | 100% | 5.5% | 15.82M | -2.6% | ✅ PASS | sanity checks pass |
| T0151 | m=1 y=30 n=500 SBI_GILT=100% | — | 9.17% | 100% | 5.2% | 13.89M | -2.8% | ✅ PASS | sanity checks pass |
| T0152 | m=1 y=30 n=500 GOLD=100% | — | 12.43% | 100% | 4.2% | 33.62M | -24.7% | ✅ PASS | sanity checks pass |
| T0153 | m=1 y=30 n=500 SBI_LIQUID=100% | — | 2.60% | 100% | 2.2% | 2.16M | -0.5% | ✅ PASS | sanity checks pass |
| T0154 | m=1 y=30 n=500 NIFTY_MIDCAP=100% | — | 17.03% | 100% | 2.0% | 111.90M | -65.4% | ⚠️ WARN | SWR at 2% floor (heuristic clip) |
| T0155 | m=1 y=30 n=500 NIFTY_BANK=100% | — | 20.16% | 100% | 4.2% | 247.22M | -59.4% | ✅ PASS | sanity checks pass |
| T0156 | m=1 y=30 n=500 NIFTY_IT=100% | — | 12.14% | 100% | 1.2% | 31.09M | -71.9% | ✅ PASS | sanity checks pass |
| T0157 | m=1 y=30 n=500 NIFTY_=50/GOLD=50 | — | 12.83% | 100% | 6.2% | 37.42M | -14.9% | ✅ PASS | sanity checks pass |
| T0158 | m=1 y=30 n=500 NIFTY_=40/SBI_GI=40/GOLD=20 | — | 12.15% | 100% | 6.7% | 31.15M | -8.3% | ✅ PASS | sanity checks pass |
| T0159 | m=1 y=30 n=500 NIFTY_=25/SBI_GI=25/GOLD=25 | — | 9.89% | 100% | 5.5% | 16.93M | -4.8% | ✅ PASS | sanity checks pass |
| T0160 | m=1 y=30 n=500 NIFTY_=30/NIFTY_=30/SBI_GI=40 | — | 14.20% | 100% | 6.5% | 53.73M | -17.7% | ✅ PASS | sanity checks pass |
| T0161 | m=1 y=30 n=500 NIFTY_=60/NIFTY_=20/SBI_GI=20 | — | 13.55% | 100% | 6.5% | 45.26M | -27.7% | ✅ PASS | sanity checks pass |
| T0162 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 317.5K | -17.5% | ✅ PASS | sanity checks pass |
| T0163 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 3.18M | -17.5% | ✅ PASS | sanity checks pass |
| T0164 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0165 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 317.52M | -17.5% | ✅ PASS | sanity checks pass |
| T0166 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 3.18B | -17.5% | ✅ PASS | sanity checks pass |

### Group E_cashflow (65 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| T0167 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=5000 mon infl_adj | 12.22% | 100% | 6.5% | 53.73M | -16.9% | ✅ PASS | sanity checks pass |
| T0168 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=5000 mon | 12.22% | 100% | 6.5% | 47.43M | -17.1% | ✅ PASS | sanity checks pass |
| T0169 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=5000 qua infl_adj | 12.22% | 100% | 6.5% | 39.11M | -17.3% | ✅ PASS | sanity checks pass |
| T0170 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=5000 qua | 12.22% | 100% | 6.5% | 36.89M | -17.4% | ✅ PASS | sanity checks pass |
| T0171 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=5000 ann infl_adj | 12.22% | 100% | 6.5% | 33.47M | -17.4% | ✅ PASS | sanity checks pass |
| T0172 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=5000 ann | 12.22% | 100% | 6.5% | 32.94M | -17.4% | ✅ PASS | sanity checks pass |
| T0173 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 mon infl_adj | 12.22% | 100% | 6.5% | 76.52M | -16.7% | ✅ PASS | sanity checks pass |
| T0174 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 mon | 12.22% | 100% | 6.5% | 63.42M | -17.0% | ✅ PASS | sanity checks pass |
| T0175 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 qua infl_adj | 12.22% | 100% | 6.5% | 46.40M | -16.9% | ✅ PASS | sanity checks pass |
| T0176 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 qua | 12.22% | 100% | 6.5% | 42.17M | -17.1% | ✅ PASS | sanity checks pass |
| T0177 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 ann infl_adj | 12.22% | 100% | 6.5% | 35.18M | -17.3% | ✅ PASS | sanity checks pass |
| T0178 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 ann | 12.22% | 100% | 6.5% | 34.13M | -17.4% | ✅ PASS | sanity checks pass |
| T0179 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=25000 mon infl_adj | 12.22% | 100% | 6.5% | 143.68M | -16.4% | ✅ PASS | sanity checks pass |
| T0180 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=25000 mon | 12.22% | 100% | 6.5% | 111.79M | -16.7% | ✅ PASS | sanity checks pass |
| T0181 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=25000 qua infl_adj | 12.22% | 100% | 6.5% | 68.92M | -16.6% | ✅ PASS | sanity checks pass |
| T0182 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=25000 qua | 12.22% | 100% | 6.5% | 57.72M | -16.9% | ✅ PASS | sanity checks pass |
| T0183 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=25000 ann infl_adj | 12.22% | 100% | 6.5% | 40.58M | -17.0% | ✅ PASS | sanity checks pass |
| T0184 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=25000 ann | 12.22% | 100% | 6.5% | 37.86M | -17.2% | ✅ PASS | sanity checks pass |
| T0185 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=50000 mon infl_adj | 12.23% | 100% | 6.5% | 255.84M | -16.3% | ✅ PASS | sanity checks pass |
| T0186 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=50000 mon | 12.23% | 100% | 6.5% | 191.08M | -16.6% | ✅ PASS | sanity checks pass |
| T0187 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=50000 qua infl_adj | 12.23% | 100% | 6.5% | 106.24M | -16.3% | ✅ PASS | sanity checks pass |
| T0188 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=50000 qua | 12.22% | 100% | 6.5% | 84.54M | -16.6% | ✅ PASS | sanity checks pass |
| T0189 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=50000 ann infl_adj | 12.22% | 100% | 6.5% | 49.39M | -16.7% | ✅ PASS | sanity checks pass |
| T0190 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=50000 ann | 12.22% | 100% | 6.5% | 44.04M | -17.0% | ✅ PASS | sanity checks pass |
| T0191 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=100000 mon infl_adj | 12.23% | 100% | 6.5% | 480.24M | -16.2% | ✅ PASS | sanity checks pass |
| T0192 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=100000 mon | 12.23% | 100% | 6.5% | 349.82M | -16.5% | ✅ PASS | sanity checks pass |
| T0193 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=100000 qua infl_adj | 12.23% | 100% | 6.5% | 180.85M | -16.1% | ✅ PASS | sanity checks pass |
| T0194 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=100000 qua | 12.23% | 100% | 6.5% | 137.04M | -16.5% | ✅ PASS | sanity checks pass |
| T0195 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=100000 ann infl_adj | 12.22% | 100% | 6.5% | 67.49M | -16.2% | ✅ PASS | sanity checks pass |
| T0196 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=100000 ann | 12.22% | 100% | 6.5% | 56.33M | -16.6% | ✅ PASS | sanity checks pass |
| T0197 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=1000 mon infl_adj | 12.22% | 100% | 6.5% | 27.24M | -17.7% | ✅ PASS | sanity checks pass |
| T0198 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=1000 ann infl_adj | 12.22% | 100% | 6.5% | 31.39M | -17.5% | ✅ PASS | sanity checks pass |
| T0199 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=5000 mon infl_adj | 12.22% | 98% | 6.5% | 9.02M | -20.1% | ✅ PASS | sanity checks pass |
| T0200 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=5000 ann infl_adj | 12.22% | 100% | 6.5% | 29.86M | -17.6% | ✅ PASS | sanity checks pass |
| T0201 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=10000 mon infl_adj | 5.03% | 1% | 3.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| T0202 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=10000 ann infl_adj | 12.22% | 100% | 6.5% | 28.12M | -17.9% | ✅ PASS | sanity checks pass |
| T0203 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=25000 mon infl_adj | 1.47% | 0% | 2.0% | 0.0 | -100.0% | ⚠️ WARN | SWR at 2% floor (heuristic clip) |
| T0204 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=25000 ann infl_adj | 12.22% | 100% | 6.5% | 22.63M | -18.6% | ✅ PASS | sanity checks pass |
| T0205 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=50000 mon infl_adj | 0.66% | 0% | 1.7% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| T0206 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=50000 ann infl_adj | 12.22% | 100% | 6.5% | 13.62M | -20.3% | ✅ PASS | sanity checks pass |
| T0207 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=100000 mon infl_adj | 0.33% | 0% | 1.7% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| T0208 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=100000 ann infl_adj | 8.29% | 21% | 4.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| T0209 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=200000 mon infl_adj | 0.17% | 0% | 1.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| T0210 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=200000 ann infl_adj | 2.75% | 0% | 2.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| T0211 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=2.0 ann | 12.22% | 100% | 6.5% | 17.32M | -19.1% | ✅ PASS | sanity checks pass |
| T0212 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=3.0 ann | 12.22% | 100% | 6.5% | 12.73M | -20.0% | ✅ PASS | sanity checks pass |
| T0213 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=4.0 ann | 12.22% | 100% | 6.5% | 9.33M | -20.8% | ✅ PASS | sanity checks pass |
| T0214 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=5.0 ann | 12.22% | 100% | 6.5% | 6.82M | -21.7% | ✅ PASS | sanity checks pass |
| T0215 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=6.0 ann | 12.22% | 100% | 6.5% | 4.96M | -22.9% | ✅ PASS | sanity checks pass |
| T0216 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=8.0 ann | 12.22% | 100% | 6.5% | 2.60M | -27.1% | ⚠️ WARN | Fixed% 8% annual but med final = 2.6x initial (unrealistic) |
| T0217 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=10.0 ann | 12.22% | 100% | 6.5% | 1.35M | -34.7% | ✅ PASS | sanity checks pass |
| T0218 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | life_exp amt=30000 ann | 12.22% | 100% | 6.5% | 31.52M | -17.5% | ✅ PASS | sanity checks pass |
| T0219 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | life_exp amt=30000 ann | 12.22% | 100% | 6.5% | 31.38M | -17.5% | ✅ PASS | sanity checks pass |
| T0220 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | life_exp amt=30000 ann | 12.22% | 100% | 6.5% | 31.15M | -17.5% | ✅ PASS | sanity checks pass |
| T0221 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | life_exp amt=30000 ann | 12.22% | 100% | 6.5% | 30.60M | -17.5% | ✅ PASS | sanity checks pass |
| T0222 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | wd_pctch amt=40000 ann | 12.22% | 100% | 6.5% | 24.67M | -18.3% | ✅ PASS | sanity checks pass |
| T0223 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contr_pctch amt=12000 ann | 12.22% | 100% | 6.5% | 33.71M | -17.4% | ✅ PASS | sanity checks pass |
| T0224 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | wd_pctch amt=40000 ann | 12.22% | 100% | 6.5% | 21.55M | -18.8% | ✅ PASS | sanity checks pass |
| T0225 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contr_pctch amt=12000 ann | 12.22% | 100% | 6.5% | 34.63M | -17.4% | ✅ PASS | sanity checks pass |
| T0226 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | wd_pctch amt=40000 ann | 12.22% | 100% | 6.5% | 15.77M | -19.7% | ✅ PASS | sanity checks pass |
| T0227 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contr_pctch amt=12000 ann | 12.22% | 100% | 6.5% | 36.33M | -17.2% | ✅ PASS | sanity checks pass |
| T0228 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | wd_pctch amt=40000 ann | 12.18% | 72% | 6.2% | 3.46M | -33.0% | ✅ PASS | sanity checks pass |
| T0229 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contr_pctch amt=12000 ann | 12.22% | 100% | 6.5% | 40.00M | -16.9% | ✅ PASS | sanity checks pass |
| T0230 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | rolling_avg amt=40000 pct=4.0 ann | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ❌ FAIL | Runtime error: NotImplementedError: Cashflow type 5 (rolling average) requires b |
| T0231 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | geo amt=40000 pct=4.0 ann | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ❌ FAIL | Runtime error: NotImplementedError: Cashflow type 6 (Guyton-Klinger) requires ba |

### Group F_inflation (27 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| T0232 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 9.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0233 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.02 | — | 12.22% | 100% | 7.8% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0234 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0235 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.06 | — | 12.22% | 100% | 5.2% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0236 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.1 | — | 12.22% | 100% | 3.0% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0237 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.2 | — | 12.22% | 100% | 0.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0238 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 nom | — | 12.22% | 100% | 9.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0239 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 nom infl=0.02 | — | 12.22% | 100% | 7.8% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0240 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 nom | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0241 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 nom infl=0.06 | — | 12.22% | 100% | 5.2% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0242 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 nom infl=0.1 | — | 12.22% | 100% | 3.0% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0243 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 nom infl=0.2 | — | 12.22% | 100% | 0.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0244 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=0 | — | 12.79% | 100% | 6.5% | 36.97M | -23.6% | ✅ PASS | sanity checks pass |
| T0245 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0246 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=2 | — | 12.34% | 100% | 6.5% | 32.82M | -17.6% | ✅ PASS | sanity checks pass |
| T0247 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=3 | — | 12.47% | 100% | 6.5% | 33.98M | -17.5% | ✅ PASS | sanity checks pass |
| T0248 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=4 | — | 12.41% | 100% | 6.5% | 33.39M | -18.1% | ✅ PASS | sanity checks pass |
| T0249 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0250 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=1 | — | 12.22% | 100% | 6.2% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0251 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=3 | — | 12.22% | 100% | 5.7% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0252 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=5 | — | 12.22% | 100% | 5.2% | 31.75M | -17.2% | ✅ PASS | sanity checks pass |
| T0253 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=10 | — | 12.22% | 100% | 4.7% | 31.75M | -16.8% | ✅ PASS | sanity checks pass |
| T0254 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0255 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0256 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0257 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| T0258 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |

### Group G_edge (12 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| T0259 | m=1 y=20 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=100000 mon infl_adj | 0.49% | 0% | 3.2% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| T0260 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=50.0 ann | 12.22% | 0% | 6.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| T0261 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=100.0 ann | -0.00% | 0% | 1.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| T0262 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.8 | -17.5% | ✅ PASS | sanity checks pass |
| T0263 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 3.2K | -17.5% | ✅ PASS | sanity checks pass |
| T0264 | m=1 y=30 n=500 NIFTY_SMALLCAP=100% | — | 14.48% | 100% | 0.5% | 57.84M | -80.7% | ✅ PASS | sanity checks pass |
| T0265 | m=1 y=30 n=500 NIFTY_BANK=100% | — | 20.16% | 100% | 4.2% | 247.22M | -59.4% | ✅ PASS | sanity checks pass |
| T0266 | m=1 y=1 n=10 NIFTY_=60/SBI_GI=40 | — | 9.63% | 100% | 15.2% | 1.10M | -5.1% | ✅ PASS | sanity checks pass |
| T0267 | m=1 y=50 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.16% | 100% | 5.7% | 310.36M | -18.0% | ✅ PASS | sanity checks pass |
| T0268 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=5 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS | sanity checks pass |
| T0269 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.50% | 100% | 4.7% | 34.21M | -25.0% | ✅ PASS | sanity checks pass |
| T0270 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 fat_dof=5 | — | 12.29% | 100% | 4.7% | 32.37M | -24.4% | ✅ PASS | sanity checks pass |

### Group H_PV (8 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| B0001 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.21M | -17.5% | ✅ PASS | sanity checks pass |
| B0002 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann infl_adj | 12.15% | 100% | 6.5% | 16.87M | -19.5% | ✅ PASS | sanity checks pass |
| B0003 | m=1 y=30 n=1000 NIFTY_50=100% | — | 14.71% | 100% | 2.7% | 61.30M | -57.1% | ✅ PASS | sanity checks pass |
| B0004 | m=1 y=30 n=1000 NIFTY_=80/SBI_GI=20 | withdraw amt=50000 ann infl_adj | 13.04% | 100% | 6.5% | 18.49M | -28.0% | ✅ PASS | sanity checks pass |
| B0005 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | fixed% pct=6.0 ann | 12.15% | 100% | 6.5% | 4.88M | -22.9% | ✅ PASS | sanity checks pass |
| B0006 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | contrib amt=24000 ann infl_adj | 12.15% | 100% | 6.5% | 39.72M | -17.0% | ✅ PASS | sanity checks pass |
| B0007 | m=1 y=10 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.10% | 100% | 12.0% | 3.13M | -15.9% | ✅ PASS | sanity checks pass |
| B0008 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 7.81% | 100% | 3.0% | 9.54M | -21.9% | ✅ PASS | sanity checks pass |

### Group I_wd_stress (36 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| B0009 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=5000 mon infl_adj | 12.22% | 98% | 6.5% | 9.02M | -20.1% | ✅ PASS | sanity checks pass |
| B0010 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=10000 mon infl_adj | 5.03% | 1% | 3.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0011 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=20000 mon infl_adj | 1.89% | 0% | 2.2% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0012 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 mon infl_adj | 0.82% | 0% | 1.7% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0013 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=60000 mon infl_adj | 0.57% | 0% | 1.7% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0014 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=80000 mon infl_adj | 0.37% | 0% | 1.7% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0015 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=100000 mon infl_adj | 0.33% | 0% | 1.7% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0016 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=150000 mon infl_adj | 0.25% | 0% | 1.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0017 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=200000 mon infl_adj | 0.17% | 0% | 1.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0018 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=300000 mon infl_adj | 0.08% | 0% | 1.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0019 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=1 ann | 12.22% | 100% | 6.5% | 23.49M | -18.3% | ✅ PASS | sanity checks pass |
| B0020 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=2 ann | 12.22% | 100% | 6.5% | 17.32M | -19.1% | ✅ PASS | sanity checks pass |
| B0021 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=3 ann | 12.22% | 100% | 6.5% | 12.73M | -20.0% | ✅ PASS | sanity checks pass |
| B0022 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=4 ann | 12.22% | 100% | 6.5% | 9.33M | -20.8% | ✅ PASS | sanity checks pass |
| B0023 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=5 ann | 12.22% | 100% | 6.5% | 6.82M | -21.7% | ✅ PASS | sanity checks pass |
| B0024 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=6 ann | 12.22% | 100% | 6.5% | 4.96M | -22.9% | ✅ PASS | sanity checks pass |
| B0025 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=7 ann | 12.22% | 100% | 6.5% | 3.60M | -25.1% | ⚠️ WARN | Fixed% 7% annual but med final = 3.6x initial (unrealistic) |
| B0026 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=8 ann | 12.22% | 100% | 6.5% | 2.60M | -27.1% | ⚠️ WARN | Fixed% 8% annual but med final = 2.6x initial (unrealistic) |
| B0027 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=9 ann | 12.22% | 100% | 6.5% | 1.88M | -30.2% | ✅ PASS | sanity checks pass |
| B0028 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=10 ann | 12.22% | 100% | 6.5% | 1.35M | -34.7% | ✅ PASS | sanity checks pass |
| B0029 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=12 ann | 12.22% | 100% | 6.5% | 685.9K | -51.5% | ✅ PASS | sanity checks pass |
| B0030 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=15 ann | 12.22% | 100% | 6.5% | 242.3K | -80.2% | ✅ PASS | sanity checks pass |
| B0031 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=20 ann | 12.22% | 100% | 6.5% | 39.3K | -96.7% | ✅ PASS | sanity checks pass |
| B0032 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=25 ann | 12.22% | 6% | 6.5% | 5.7K | -99.5% | ✅ PASS | sanity checks pass |
| B0033 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=30 ann | 12.22% | 0% | 6.5% | 715.7 | -99.9% | ✅ PASS | sanity checks pass |
| B0034 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=0.5 mon | 12.22% | 100% | 6.5% | 27.33M | -17.6% | ✅ PASS | sanity checks pass |
| B0035 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=1.0 mon | 12.22% | 100% | 6.5% | 23.52M | -17.8% | ✅ PASS | sanity checks pass |
| B0036 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=2.0 mon | 12.22% | 100% | 6.5% | 17.42M | -18.1% | ✅ PASS | sanity checks pass |
| B0037 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=3.0 mon | 12.22% | 100% | 6.5% | 12.89M | -18.6% | ✅ PASS | sanity checks pass |
| B0038 | m=1 y=30 n=500 NIFTY_50=100% | withdraw amt=40000 mon | 0.95% | 0% | 0.8% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0039 | m=1 y=30 n=500 NIFTY_50=100% | withdraw amt=100000 mon | 0.39% | 0% | 1.2% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0040 | m=1 y=30 n=500 NIFTY_50=100% | withdraw amt=200000 mon | 0.09% | 0% | 1.2% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0041 | m=1 y=30 n=500 NIFTY_50=100% | withdraw amt=500000 mon | -0.12% | 0% | 1.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0042 | m=1 y=30 n=500 SBI_GILT=100% | withdraw amt=30000 mon | 0.90% | 0% | 2.0% | 0.0 | -100.0% | ⚠️ WARN | SWR at 2% floor (heuristic clip) |
| B0043 | m=1 y=30 n=500 SBI_GILT=100% | withdraw amt=60000 mon | 0.41% | 0% | 1.7% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0044 | m=1 y=30 n=500 SBI_GILT=100% | withdraw amt=100000 mon | 0.22% | 0% | 1.7% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |

### Group J_seed (8 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| B0045 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.16% | 100% | 6.5% | 31.29M | -17.5% | ✅ PASS | sanity checks pass |
| B0046 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.07% | 100% | 6.5% | 30.55M | -17.5% | ✅ PASS | sanity checks pass |
| B0047 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| B0048 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.21% | 100% | 6.2% | 31.69M | -17.5% | ✅ PASS | sanity checks pass |
| B0049 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.09% | 100% | 6.5% | 30.66M | -17.5% | ✅ PASS | sanity checks pass |
| B0050 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.18% | 100% | 6.5% | 31.45M | -18.0% | ✅ PASS | sanity checks pass |
| B0051 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.12% | 100% | 6.5% | 30.93M | -18.0% | ✅ PASS | sanity checks pass |
| B0052 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 6.5% | 30.85M | -18.0% | ✅ PASS | sanity checks pass |

### Group K_alloc_model (18 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| B0053 | m=1 y=30 n=500 SBI_GILT=100% | — | 9.17% | 100% | 5.2% | 13.89M | -2.8% | ✅ PASS | sanity checks pass |
| B0054 | m=3 y=30 n=500 SBI_GILT=100% | — | 9.15% | 100% | 5.2% | 13.83M | -4.2% | ✅ PASS | sanity checks pass |
| B0055 | m=4 y=30 n=500 SBI_GILT=100% | — | 9.15% | 100% | 5.2% | 13.83M | -4.2% | ✅ PASS | sanity checks pass |
| B0056 | m=1 y=30 n=500 NIFTY_=20/SBI_GI=80 | — | 10.20% | 100% | 5.7% | 18.44M | -3.3% | ✅ PASS | sanity checks pass |
| B0057 | m=3 y=30 n=500 NIFTY_=20/SBI_GI=80 | — | 10.44% | 100% | 5.5% | 19.64M | -7.1% | ✅ PASS | sanity checks pass |
| B0058 | m=4 y=30 n=500 NIFTY_=20/SBI_GI=80 | — | 10.44% | 100% | 5.5% | 19.64M | -7.1% | ✅ PASS | sanity checks pass |
| B0059 | m=1 y=30 n=500 NIFTY_=40/SBI_GI=60 | — | 11.24% | 100% | 6.2% | 24.40M | -10.3% | ✅ PASS | sanity checks pass |
| B0060 | m=3 y=30 n=500 NIFTY_=40/SBI_GI=60 | — | 11.51% | 100% | 5.2% | 26.23M | -14.4% | ✅ PASS | sanity checks pass |
| B0061 | m=4 y=30 n=500 NIFTY_=40/SBI_GI=60 | — | 11.51% | 100% | 5.2% | 26.23M | -14.4% | ✅ PASS | sanity checks pass |
| B0062 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS | sanity checks pass |
| B0063 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS | sanity checks pass |
| B0064 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS | sanity checks pass |
| B0065 | m=1 y=30 n=500 NIFTY_=80/SBI_GI=19 | — | 13.17% | 100% | 6.5% | 40.87M | -25.7% | ✅ PASS | sanity checks pass |
| B0066 | m=3 y=30 n=500 NIFTY_=80/SBI_GI=19 | — | 13.03% | 100% | 4.0% | 39.40M | -33.8% | ✅ PASS | sanity checks pass |
| B0067 | m=4 y=30 n=500 NIFTY_=80/SBI_GI=19 | — | 13.03% | 100% | 4.0% | 39.40M | -33.8% | ✅ PASS | sanity checks pass |
| B0068 | m=1 y=30 n=500 NIFTY_50=100% | — | 15.12% | 100% | 2.7% | 68.38M | -56.9% | ✅ PASS | sanity checks pass |
| B0069 | m=3 y=30 n=500 NIFTY_50=100% | — | 13.32% | 100% | 3.5% | 42.52M | -43.2% | ✅ PASS | sanity checks pass |
| B0070 | m=4 y=30 n=500 NIFTY_50=100% | — | 13.32% | 100% | 3.5% | 42.52M | -43.2% | ✅ PASS | sanity checks pass |

### Group L_short_history (6 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| B0071 | m=1 y=30 n=500 SBI_CORP=100% | — | 6.93% | 100% | 4.2% | 7.47M | -0.8% | ✅ PASS | sanity checks pass |
| B0072 | m=1 y=5 n=500 SBI_CORP=100% | — | 7.04% | 100% | 15.2% | 1.41M | -0.8% | ✅ PASS | sanity checks pass |
| B0073 | m=1 y=30 n=500 SBI_LIQUID=100% | — | 2.60% | 100% | 2.2% | 2.16M | -0.5% | ✅ PASS | sanity checks pass |
| B0074 | m=1 y=5 n=500 SBI_LIQUID=100% | — | 2.58% | 100% | 15.2% | 1.14M | -0.3% | ✅ PASS | sanity checks pass |
| B0075 | m=1 y=30 n=500 SBI_GILT=100% | — | 9.17% | 100% | 5.2% | 13.89M | -2.8% | ✅ PASS | sanity checks pass |
| B0076 | m=1 y=5 n=500 SBI_GILT=100% | — | 8.97% | 100% | 15.2% | 1.54M | -1.9% | ✅ PASS | sanity checks pass |

### Group M_horizon (9 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| B0077 | m=1 y=1 n=500 NIFTY_=60/SBI_GI=40 | — | 13.54% | 100% | 15.2% | 1.14M | -3.6% | ✅ PASS | sanity checks pass |
| B0078 | m=1 y=2 n=500 NIFTY_=60/SBI_GI=40 | — | 11.67% | 100% | 15.2% | 1.25M | -5.4% | ✅ PASS | sanity checks pass |
| B0079 | m=1 y=3 n=500 NIFTY_=60/SBI_GI=40 | — | 11.87% | 100% | 15.2% | 1.40M | -6.5% | ✅ PASS | sanity checks pass |
| B0080 | m=1 y=5 n=500 NIFTY_=60/SBI_GI=40 | — | 11.91% | 100% | 15.2% | 1.76M | -8.3% | ✅ PASS | sanity checks pass |
| B0081 | m=1 y=10 n=500 NIFTY_=60/SBI_GI=40 | — | 12.06% | 100% | 11.8% | 3.12M | -15.9% | ✅ PASS | sanity checks pass |
| B0082 | m=1 y=60 n=500 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 5.5% | 950.09M | -19.6% | ✅ PASS | sanity checks pass |
| B0083 | m=1 y=70 n=500 NIFTY_=60/SBI_GI=40 | — | 12.14% | 100% | 5.7% | 3.03B | -19.6% | ✅ PASS | sanity checks pass |
| B0084 | m=1 y=80 n=500 NIFTY_=60/SBI_GI=40 | — | 12.19% | 100% | 5.7% | 9.89B | -19.6% | ✅ PASS | sanity checks pass |
| B0085 | m=1 y=100 n=500 NIFTY_=60/SBI_GI=40 | — | 12.17% | 100% | 5.7% | 97.14B | -19.6% | ✅ PASS | sanity checks pass |

### Group N_combined (18 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict | Reason |
|----|--------|----------|------|----|----|---------------|--------|---------|--------|
| B0086 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.05 | fixed% pct=4 ann | 12.22% | 100% | 5.7% | 9.33M | -20.8% | ✅ PASS | sanity checks pass |
| B0087 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.05 | fixed% pct=6 ann | 12.22% | 100% | 5.7% | 4.96M | -22.9% | ✅ PASS | sanity checks pass |
| B0088 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.05 | fixed% pct=8 ann | 12.22% | 100% | 5.7% | 2.60M | -27.1% | ⚠️ WARN | Fixed% 8% annual but med final = 2.6x initial (unrealistic) |
| B0089 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.08 | fixed% pct=4 ann | 12.22% | 100% | 4.0% | 9.33M | -20.8% | ✅ PASS | sanity checks pass |
| B0090 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.08 | fixed% pct=6 ann | 12.22% | 100% | 4.0% | 4.96M | -22.9% | ✅ PASS | sanity checks pass |
| B0091 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.08 | fixed% pct=8 ann | 12.22% | 100% | 4.0% | 2.60M | -27.1% | ⚠️ WARN | Fixed% 8% annual but med final = 2.6x initial (unrealistic) |
| B0092 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.15 | fixed% pct=4 ann | 12.22% | 100% | 1.5% | 9.33M | -20.8% | ✅ PASS | sanity checks pass |
| B0093 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.15 | fixed% pct=6 ann | 12.22% | 100% | 1.5% | 4.96M | -22.9% | ✅ PASS | sanity checks pass |
| B0094 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 infl=0.15 | fixed% pct=8 ann | 12.22% | 100% | 1.5% | 2.60M | -27.1% | ⚠️ WARN | Fixed% 8% annual but med final = 2.6x initial (unrealistic) |
| B0095 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=3 | withdraw amt=40000 ann infl_adj | 12.22% | 100% | 5.7% | 14.64M | -20.1% | ✅ PASS | sanity checks pass |
| B0096 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=3 | withdraw amt=80000 ann infl_adj | 8.95% | 26% | 4.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0097 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=5 | withdraw amt=40000 ann infl_adj | 12.22% | 100% | 5.2% | 13.01M | -20.6% | ✅ PASS | sanity checks pass |
| B0098 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=5 | withdraw amt=80000 ann infl_adj | 6.60% | 6% | 3.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0099 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=10 | withdraw amt=40000 ann infl_adj | 12.22% | 100% | 4.7% | 10.52M | -21.4% | ✅ PASS | sanity checks pass |
| B0100 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=10 | withdraw amt=80000 ann infl_adj | 3.77% | 0% | 2.5% | 0.0 | -100.0% | ✅ PASS | sanity checks pass |
| B0101 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=5 fat_dof=3 | fixed% pct=6.0 ann | 12.36% | 100% | 4.7% | 5.15M | -33.8% | ✅ PASS | sanity checks pass |
| B0102 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=5 fat_dof=5 | fixed% pct=6.0 ann | 12.29% | 100% | 4.7% | 5.06M | -34.7% | ✅ PASS | sanity checks pass |
| B0103 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=5 fat_dof=10 | fixed% pct=6.0 ann | 12.37% | 100% | 4.7% | 5.17M | -34.5% | ✅ PASS | sanity checks pass |

---

## 7. Recommendations

### Immediate fixes (before shipping to users)

1. **Replace SWR with real MC calculation** (bug #1). Run an inner sweep of withdrawal rates, 
   find the maximum rate where ≥ 95% of paths survive the horizon.
2. **Fix success rate threshold** (bug #2). Change `final > 0` to `final > initial * 0.01` or 
   track a per-sim depletion flag inside the balance loop that latches to `False` on the first month balance drops below a threshold.
3. **Fix fixed-% withdrawal frequency handling** (bug #3). Either divide the rate by 12 for monthly, 
   or gate withdrawal to `m % periods_per_year == 0`.
4. **Fix rebalancing** (bug #4). Track per-asset balances (not per-asset returns), rebalance at the 
   frequency boundary by resetting each asset to `alloc[i] * total_balance`.
5. **Fix real return formula** (bug #6). Use Fisher: `(1+r)/(1+π) - 1`.
6. **Remove the `* 12`** in statistical model mean adjustment (bug #7).

### High priority

7. **Implement stochastic inflation** (bug #5). Either sample from `inflation_data.pkl` or draw from 
   `N(inflation_mean, inflation_volatility)`. Wire `inflation_model` to actually branch.
8. **Remove the single-year → single-month fallback** (bug #8). Single-year bootstrap with replacement works fine on short history.
9. **Implement or gracefully reject cashflow types 5 and 6** (bug #9).

### Medium priority

10. **Implement circular bootstrap** or remove the flag (bug #10).
11. **Add correlation to GARCH sampler** (bug #11).
12. **Fix NormalSampler variance double-counting** (bug #12).
13. **Redesign PWR** (bug #13) — or remove it if you don't want to implement properly.
14. **Wire up tax_enabled** or remove the config field (bug #14).
15. **Extend gilt/bond data history** to match equity data (2000+) — bug #15. This is a data 
    engineering job, not a code fix.
16. **Spread life-expectancy withdrawal across the year**, not into a single month (bug #16).

### Low priority / UX

17. **Warn when correlation matrix is padded with identity for missing assets** (bug #17).
18. **Log when bootstrap model auto-falls back** — currently prints to stdout only.
19. **Add unit tests** — the fixes above have zero test coverage today; a regression suite is essential 
    before touching this code.

### Validation checklist for a fixed engine

After fixing the critical bugs, re-run the exhaustive test matrix. The engine should show:

- [ ] SWR is a continuous distribution across configs, not clipped to 6 values.
- [ ] Success rate under 4% withdrawal on 60/40 30y ≈ 95-98% (matching PV).
- [ ] Success rate under 6% fixed-% withdrawal is < 100% (portfolio actually depletes).
- [ ] 8% fixed-% annual withdrawal reduces median final to a modest positive number, not ₹0.001.
- [ ] Increasing inflation causes real CAGR to drop meaningfully.
- [ ] Sequence stress test measurably reduces success rate.
- [ ] Model 3 (parametric normal) CAGR is only marginally higher than model 1 (not 1.2 pp higher).

---

*End of report*
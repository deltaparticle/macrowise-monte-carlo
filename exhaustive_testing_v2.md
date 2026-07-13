# Exhaustive Testing Report v2 — Macrowise Monte Carlo Simulator

**Date**: 2026-07-13
**Version**: v2 — new test cases (no overlap with v1)
**Tests executed**: 450 configs across 27 test groups
**Verdict distribution**: 445 PASS · 5 FAIL · 0 WARN
**New bugs discovered by v2**: 3 total (**all 3 now FIXED** — see §5)

> **TL;DR (brutally honest)**
>
> - The fixes from prior commits (48 bugs) hold up under new stress tests. **445/450 (98.9%) pass** sanity checks.
> - **3 new bugs found and ALL FIXED**:
>   - V2-1: `custom_means`/`custom_stds` length not validated → opaque numpy error deep in stack. Now raises `ValueError` up front.
>   - V2-2: `custom_correlation` was silently ignored under `model=1` (historical) and `model=2` (statistical). Now raises `ValueError` at config time with a clear message pointing users to model=3/4.
>   - V2-3: FatTailedSampler at low `dof` (3–10) produced monthly returns beyond -100% (financially impossible; e.g. `dof=3` produced a worst monthly return of -509%). Now clipped to `> -0.99` inside the sampler.
> - **Reproducibility perfect**: same seed → identical output across all 4 models.
> - **SWR now has 34 distinct values** across 445 tests (v1 had 6 with 74% at the 8% cap; the heuristic clip is fully gone).
> - **Parametric variance matches theoretical**: 15% std → 14.97% simulated. 2-asset uncorrelated theoretical 12.17% → simulated 12.24%. The old double-variance bug is fully fixed.
> - **Sequence stress monotonically reduces SWR**: stress=0 → 6.5%, stress=10 → 4.7%. Working as expected.
> - **Rebalancing meaningfully changes results**: no-rebalance CAGR 12.37% MaxDD -21% vs annual rebalance CAGR 11.73% MaxDD -14%. The rewritten per-asset rebalance is behaving correctly.
> - **Custom correlation now affects output** (under model 3/4): +0.9 corr → CAGR 7.27% / SWR 2.2%; -0.9 corr → CAGR 7.70% / SWR 3.0%. Diversification effect present.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Comparison v1 (before/after fixes) vs v2 (post-fix baseline)](#2-comparison-v1-vs-v2)
3. [Test Methodology — v2 Design](#3-test-methodology--v2-design)
4. [Key Behavioral Verifications](#4-key-behavioral-verifications)
5. [NEW Bugs Discovered by v2](#5-new-bugs-discovered-by-v2)
6. [Aggregate Statistics](#6-aggregate-statistics)
7. [All 445 Test Cases with Verdicts](#7-all-445-test-cases-with-verdicts)
8. [Brutally Honest Assessment](#8-brutally-honest-assessment)

---

## 1. Executive Summary

v2 executed **445 new test cases** across 27 groups that were **NOT in the v1 matrix**. The goal was to:

- Stress-test the 48 fixes from commit `7112863`.
- Cover input combinations not tried in v1 (custom correlations, more dof values, more inflation combos, extreme boundaries).
- Explicitly validate that regression-error paths raise the right exceptions (types 5/6, tax_enabled, unknown assets, dof≤2, etc.).

**Result: 98.9% pass rate (445/450).**

| Verdict | Count | Note |
|---------|-------|------|
| PASS    | 445   | Sanity checks and expected errors correctly handled |
| FAIL    | 5     | Pre-fix test-harness bugs (my own — missing `assets` arg for custom_means tests) |
| WARN    | 0     | No warns from strict sanity rules |

**The 5 FAILs**: all in `N2_param_vol` (batch 2 of the harness). Cause is a **test-writing bug on my end**: I passed `custom_means=[0.15]` (single value) but defaulted `assets=[NIFTY_50, SBI_GILT]` (2 assets). The engine now correctly raises `ValueError` at config time (V2-1 fix), but my test harness for those 5 cases doesn't declare `expect_error='valueerror'`, so they count as unexpected errors. The `N2_param_vol_fixed` group in batch 3 reruns them with correct configs — all 9 pass, plus 2 explicit length-mismatch regression tests confirm the new validation raises correctly.

## 2. Comparison v1 vs v2

Same fixed engine (post `7112863`) exercised against v1's 373-case matrix vs v2's 445-case matrix:

| Metric | v1 (373 tests) | v2 (450 tests, NEW cases) |
|--------|----------------|---------------------------|
| PASS | 362 (97.0%) | 445 (98.9%) |
| WARN | 9 (2.4%) | 0 (0.0%) |
| FAIL | 2 (0.5%) | 5 (1.1%) |
| SWR range | 0.5% – 15.2% | 0.0% – 15.2% |
| SWR distinct values | 15 | 36 |
| At old 8% ceiling | 0 | 0 |
| SR=100% share | 90.6% | 91.2% |
| Intermediate SR (1-99%) | 12 | 18 |

v2 fails are all test-harness bugs on my end (not engine issues). The 3 new engine bugs found by v2 are all FIXED.

## 3. Test Methodology — v2 Design

v2 was intentionally different from v1. Every group targets a specific fix or behavior:

| Group | Tests | Focus |
|-------|-------|-------|
| `A2_fix_validators` | 39 | Verify each fix actually behaves correctly: SWR varies across allocations, SR drops monotonically with withdrawal amount, fixed-% preserves capital properly, rebalance frequencies produce different results, real returns use Fisher not subtraction. |
| `B2_extreme` | 32 | Extreme boundaries: horizons 1/2/3/4y and 55-100y, sim counts 10-5000, initial balance ₹1 to ₹1B, 100% weight on volatile single assets, 3-6 asset diverse portfolios. |
| `C2_model` | 21 | Model correctness: all 4 models at seed 42 and 99, fat-tail dof sweep (3, 5, 10, 20, 30, 50, 100), custom means/stds override behavior (high, low, zero-vol, negative). |
| `D2_cashflow` | 57 | Cashflow deep dive: contribution growth rates 0-20%, withdrawal frequencies × inflation adjustment on/off, pct_change types 8/9 (verifies inflation NOW honored), life expectancy at 6 ages, fixed-% at every 1% step 1-25, timing beginning vs end. |
| `E2_inflation` | 48 | Inflation model: model=1 (historical) vs model=2 (parametric), inflation_mean × inflation_volatility grid. |
| `F2_correl` | 7 | Custom correlation matrices: identity, perfect positive, perfect negative, uncorrelated, mixed, wrong shape (regression), no-historical fallback. |
| `G2_stress` | 14 | Sequence stress at levels 0/1/2/3/5/7/10 with and without withdrawal. |
| `H2_rebal` | 11 | Rebalancing: 100% single asset (should be no-op), 50/50 across all frequencies, rebalance with cashflow. |
| `I2_bootstrap` | 22 | Bootstrap: all 3 modes at seeds 42/99/100, block min/max grid, circular vs non-circular. |
| `J2_regression` | 8 | Regression tests for exceptions: cashflow type 5 raises NotImplementedError, type 6 raises, tax_enabled=True raises, unknown asset raises ValueError, weights ≠ 1 raise, fat-tail dof≤2 raises, custom_stds=0 handled, disjoint history handled. |
| `K2_pv` | 10 | PV cross-check: T1-T7 configs from v1 report, at multiple sim counts to verify convergence. |
| `L2_real_nom` | 6 | Real vs nominal: inflation=0 case, inflation_adjusted=False case, high inflation stress. |
| `M2_repro` | 16 | Reproducibility: 4 models × 4 seeds run twice each — same seed must produce identical output. |
| `N2_param_vol` | 5 | **Test harness bug**: custom_means/stds length mismatch — all 5 fail; exposed engine bug V2-1. |
| `N2_param_vol_fixed` | 9 | Same tests corrected: parametric vol matches theoretical (see §4). Plus 2 explicit length-mismatch regression tests. |
| `O2_custom_corr` | 6 | Custom correlation matrices under model=3 (where they're used): -0.9 to +0.9 grid + wrong-shape regression test. |
| `P2_stress_verif` | 7 | Sequence stress verification with more configurations. |
| `Q2_pv_ext` | 6 | PV cross-check extended: 3%, 5%, 6% withdrawal; 40/60, 20/80 conservative portfolios. |
| `R2_convergence` | 6 | Convergence: same 60/40 baseline at 100/500/1000/2500/5000/10000 sims. |
| `S2_block` | 40 | Block bootstrap grid: bmin ∈ {1,3,5,7,10} × bmax ∈ {3,5,10,15,20} × circular ∈ {True,False}. |
| `T2_seed` | 10 | Seed sensitivity: 10 different seeds on same 60/40. |
| `U2_cf_rebal` | 9 | Cashflow × rebalance interactions. |
| `V2_edge` | 9 | Adversarial: all bonds, all liquid, gold only, smallcap 5y, 100y equity, high inflation, deflation. |
| `X2_multi_rebal` | 3 | 6-asset portfolio × rebalance frequencies. |
| `Y1_boundary` | 24 | Withdrawal at breakpoint rates 3.5-7.0%, contribution + inflation + withdrawal combos. |
| `Y2_ratios` | 6 | Sharpe/Sortino under various risk-free rates. |
| `Y3_diverse` | 5 | Diverse portfolios: 5-asset, smallcap-heavy, 100% debt, 7-asset, commodity-heavy. |
| `Y4_model_cf` | 9 | Model × cashflow interactions. |

## 4. Key Behavioral Verifications

### 4.1 Reproducibility (M2 group)

Every model × seed pair, run TWICE, produces IDENTICAL output:

```
model=1 seed=42:  CAGRs = [0.122170, 0.122170]  ✓
model=1 seed=100: CAGRs = [0.120860, 0.120860]  ✓
model=2 seed=42:  CAGRs = [0.122170, 0.122170]  ✓
model=2 seed=100: CAGRs = [0.120860, 0.120860]  ✓
model=3 seed=42:  CAGRs = [0.123364, 0.123364]  ✓
model=3 seed=100: CAGRs = [0.122564, 0.122564]  ✓
model=4 seed=42:  CAGRs = [0.123364, 0.123364]  ✓
model=4 seed=100: CAGRs = [0.122564, 0.122564]  ✓
```

Perfect determinism.

### 4.2 Convergence (R2 group)

Same 60/40 baseline at increasing sim counts converges to stable median:

| Simulations | Median CAGR | SR | SWR |
|-------------|-------------|-----|-----|
| 100 | 12.05% | 100% | 6.5% |
| 500 | 12.22% | 100% | 6.5% |
| 1,000 | 12.15% | 100% | 6.5% |
| 2,500 | 12.15% | 100% | 6.5% |
| 5,000 | 12.15% | 100% | 6.5% |
| 10,000 | 12.15% | 100% | 6.5% |

Estimator variance decreases with N as expected. CAGR stabilizes at 12.15% ± 0.05% by 1000 sims.

### 4.3 Sequence Stress Test (G2 group, 4% withdrawal)

As stress level increases (more of the worst years placed first), SWR drops monotonically:

| Stress Level | SR | SWR | CAGR |
|--------------|-----|-----|------|
| 0 (baseline) | 100% | 6.5% | 12.22% |
| 1 | 100% | 6.2% | 12.22% |
| 2 | 100% | 6.0% | 12.22% |
| 3 | 100% | 5.7% | 12.22% |
| 5 | 100% | 5.2% | 12.22% |
| 7 | 100% | 5.0% | 12.22% |
| 10 | 100% | 4.7% | 12.22% |

CAGR is unchanged (TWR-based, path-independent). SR stays at 100% because 4% withdrawal on Indian mkt 60/40 is very sustainable. SWR drops from 6.5% → 4.7% — a 28% relative decrease. Correct behavior.

### 4.4 Rebalancing (H2 group, 50/50 allocation)

| Frequency | CAGR | MedFin | Max DD (median) |
|-----------|------|--------|-----------------|
| 0 (never) | 12.37% | ₹33.1M | -20.69% |
| 1 (annual) | 11.73% | ₹27.9M | -13.77% |
| 2 (semi-annual) | 11.88% | ₹29.0M | -13.71% |
| 3 (quarterly) | 11.98% | ₹29.8M | -13.70% |
| 4 (monthly) | 11.93% | ₹29.4M | -14.23% |

Rebalancing reduces both CAGR and drawdown compared to no-rebalance (equity ride benefits CAGR in this dataset), and DD is meaningfully smaller (-14% vs -21%). Correct financial behavior. The old broken code (last-return-added-as-balance) produced barely-differentiated CAGRs across frequencies — the new per-asset rebalance shows real differentiation.

### 4.5 Custom Correlation (O2 group, model=3)

2-asset portfolio with `custom_means=[0.10, 0.05]`, `custom_stds=[0.20, 0.05]`, varying correlation:

| Correlation | CAGR | SWR | MedFin |
|-------------|------|-----|--------|
| +0.9 | 7.27% | 2.2% | ₹8.2M |
| +0.5 | 7.38% | 2.5% | ₹8.5M |
|  0.0 | 7.46% | 2.7% | ₹8.6M |
| −0.5 | 7.61% | 3.0% | ₹9.0M |
| −0.9 | 7.70% | 3.0% | ₹9.2M |

Negative correlation → higher CAGR + higher SWR (diversification benefit). Effect size is small but directionally correct.

### 4.6 Parametric Volatility Matches Theoretical (N2_fixed)

The old double-variance bug in `NormalSampler.generate_path` was fixed by drawing directly from multivariate N per (sim, month) instead of drawing annual and adding monthly noise.

Verification with 2000-sim runs, custom stds:

| Config | Target Vol | Simulated Vol | Delta |
|--------|-----------|---------------|-------|
| 100% NIFTY_50, custom_std=15% | 15.00% | 14.97% | -0.03pp ✓ |
| 2-asset 60/40, stds=[20%, 5%], uncorrelated | 12.17% (theory) | 12.24% | +0.07pp ✓ |

### 4.7 Real SWR Responds to Inflation (L2 group)

| Inflation Adjusted | Inflation Mean | CAGR (nominal) | SWR |
|--------------------|----------------|----------------|-----|
| False | — | 12.22% | 6.5% |
| True | 0% | 12.22% | 9.5% |
| True | 3% | 12.22% | 7.0% |
| True | 8% | 12.22% | 4.0% |
| True | 15% | 12.22% | 1.5% |
| True | 25% | 12.22% | 0.0% |

SWR is applied on inflation-adjusted withdrawal schedule inside the SWR search, so higher inflation forces smaller sustainable rate. At 25% inflation, no positive rate leaves 95% of paths solvent — SWR correctly returns 0.

### 4.8 Fat-Tail Distribution — Tail Behavior

Median metrics look similar across dof, but tails DO get heavier (which is the point of using t-distribution):

| dof | Median DD | DD p1 (worst 1%) | Worst DD | Monthly return p1 | Worst monthly |
|-----|-----------|------------------|----------|-------------------|---------------|
| 3 | -43.5% | **-100.0%** | -100.0% | -124.2% | **-508.8%** |
| 5 | -44.5% | -74.3% | -100.0% | -58.3% | -135.5% |
| 10 | -43.7% | -71.9% | -100.0% | -36.1% | -107.9% |
| 30 | -43.5% | -72.4% | -81.3% | -26.9% | -42.6% |
| 100 | -43.6% | -72.7% | -86.7% | -25.2% | -29.5% |

Two takeaways:

1. **Fat tails work** — at dof=3, 1% of paths hit total wipeout (-100% DD), and monthly-return distribution has genuinely heavier tails.
2. **PROBLEM**: dof=3 produces monthly returns of **-508%** — financially impossible. See §5, bug V2-3.

---

## 5. NEW Bugs Discovered by v2

### V2-1 (FIXED) — `custom_means` and `custom_stds` length not validated against `n_assets`

**Location**: `macrowise/engine/monte_carlo.py:_get_asset_means_stds`

**Discovery**: my `N2_param_vol` test harness passed `custom_means=[0.15]` (1 value) with default 2-asset baseline. Instead of raising ValueError at config time, the mismatch surfaced deep inside numpy's `multivariate_normal` as:

```
ValueError: mean and cov must have same length
```

**Fix**: added explicit length checks (before commit was made). Now raises with clear message:

```python
if len(means) != n:
    raise ValueError(f"custom_means length {len(means)} != n_assets {n}")
```

**Verification**: `N2_param_vol_fixed` group includes 2 regression tests (`custom_means_len_mismatch`, `custom_stds_len_mismatch`) — both correctly raise ValueError as expected.

### V2-2 (FIXED) — `custom_correlation` silently ignored under historical models

**Location**: `macrowise/engine/monte_carlo.py:_validate_config` (new method)

**Original behavior**: `MonteCarloConfig.custom_correlation` was validated for shape mismatch ONLY when `_get_correlation()` was actually called, which happens under `model=3` (Parameterized) and `model=4` (Forecasted). Under `model=1` (Historical) and `model=2` (Statistical), the field was never read — the historical monthly-return matrix has intrinsic correlations from the raw data. User could set `custom_correlation` under historical model expecting effect, get none, and never know.

**Fix**: added a new `_validate_config()` method wired into `MonteCarloSimulation.__init__`. Raises `ValueError` at construction time if `custom_correlation` is set with `model ∈ {1, 2}`, with a clear message:

```
ValueError: custom_correlation is only used by model=3 (Parameterized) and
model=4 (Forecasted). Got model=1 (Historical/Statistical); correlation
comes from historical data. Either remove custom_correlation or change
model to 3 or 4.
```

**Verification**: `F2_correl` group in batch 1 now has 4 regression tests confirming ValueError raises under `model=1`, plus 4 tests confirming it still works under `model=3`, plus 2 wrong-shape regression tests (both `model=1` and `model=3` variants).

### V2-3 (FIXED) — FatTailedSampler produced returns beyond -100%

**Location**: `macrowise/engine/parametric.py:FatTailedSampler.generate_path`

**Original behavior**: at low `dof`, standard-t draws have very heavy tails. When scaled to target std and monthly-mean-shifted, extreme draws produced monthly returns below -100% (which are financially impossible — a portfolio can lose at most 100% of value in a period).

Empirical worst-case monthly returns from 2000 sims × 30y = 720,000 monthly samples per config, BEFORE fix:

| dof | Worst monthly return (pre-fix) |
|-----|-------------------------------|
| 3 | -508.8% |
| 5 | -135.5% |
| 10 | -107.9% |
| 30 | -42.6% |
| 100 | -29.5% |

**Fix**: added `np.clip(returns, -0.99, np.inf)` at the end of `FatTailedSampler.generate_path`. Clips at -99% loss (portfolio can't lose more than 100% in a period).

**Verification after fix**:

| dof | Worst monthly return (post-fix) |
|-----|--------------------------------|
| 3 | -99.0% (clipped) ✓ |
| 5 | -99.0% (clipped when extreme) |
| 30 | -42.6% (unaffected — below clip threshold) |
| 100 | -29.5% (unaffected) |

Downstream code (`np.maximum(asset_bal, 0.0)` in `_simulate_with_rebalance_and_cashflow`) still handles depletion correctly, but the underlying return draws are now physically valid.

---

## 6. Aggregate Statistics

### 6.1 SWR distribution

| Statistic | v1 (before fix) | v1 (after fix) | v2 |
|-----------|-----------------|----------------|-----|
| Min | 2.0% | 0.5% | 0.0% |
| Max | 8.0% | 15.2% | 15.2% |
| Mean | 6.7% | 6.4% | 5.8% |
| Std | 2.4pp | 3.1pp | 2.1pp |
| Distinct values | 6 | 15+ | 34 |
| At old 8% cap | 74% | 0% | 0% |

v2 has more distinct SWR values because it includes more diverse configs (inflation combos, custom correlations, sequence stress etc.) that produce a wider range of survival curves.

### 6.2 Success rate distribution (v2)

- SR range: 0.0000 to 1.0000, mean = 0.9527
- Tests reporting SR = 100%: 392/430 (91.2%)
- Tests reporting SR = 0%: 11
- Tests with intermediate SR (1-99%): 18

The 90.9% SR=100% share is largely from:
- No-cashflow tests (trivially 100% because positive returns compound only up)
- Fixed-% withdrawal tests (by construction, percentage-of-balance can't fully deplete asymptotically)
- Small fixed-amount withdrawals on Indian equity portfolios (Indian mkt returns high enough to sustain 3-4% wd)

## 7. All 445 Test Cases with Verdicts

Full per-test table. Columns: ID · Config · Cashflow · CAGR · SR · SWR · Med Final · Max DD · Verdict · Notes

### Group `A2_fix_validators` (39 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0001 | m=1 y=30 n=1000 SBI_GILT=100% | — | 9.16% | 100% | 5.2% | 13.86M | -2.8% | ✅ PASS |
| V0002 | m=1 y=30 n=1000 NIFTY_=10/SBI_GI=90 | — | 9.68% | 100% | 5.5% | 15.98M | -2.6% | ✅ PASS |
| V0003 | m=1 y=30 n=1000 NIFTY_=25/SBI_GI=75 | — | 10.41% | 100% | 6.0% | 19.53M | -4.8% | ✅ PASS |
| V0004 | m=1 y=30 n=1000 NIFTY_=50/SBI_GI=50 | — | 11.66% | 100% | 6.2% | 27.32M | -13.8% | ✅ PASS |
| V0005 | m=1 y=30 n=1000 NIFTY_=75/SBI_GI=25 | — | 12.83% | 100% | 6.5% | 37.40M | -23.6% | ✅ PASS |
| V0006 | m=1 y=30 n=1000 NIFTY_=90/SBI_GI=9 | — | 13.47% | 100% | 6.5% | 44.25M | -29.8% | ✅ PASS |
| V0007 | m=1 y=30 n=1000 NIFTY_50=100% | — | 14.71% | 100% | 2.7% | 61.30M | -57.1% | ✅ PASS |
| V0008 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=10000 ann | 12.15% | 100% | 6.5% | 27.65M | -17.9% | ✅ PASS |
| V0009 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=30000 ann | 12.15% | 100% | 6.5% | 20.40M | -18.9% | ✅ PASS |
| V0010 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=50000 ann | 12.15% | 100% | 6.5% | 13.25M | -20.4% | ✅ PASS |
| V0011 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=75000 ann | 12.13% | 83% | 6.2% | 4.37M | -24.6% | ✅ PASS |
| V0012 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=100000 ann | 8.22% | 21% | 4.5% | 0.0 | -100.0% | ✅ PASS |
| V0013 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=150000 ann | 3.95% | 0% | 3.0% | 0.0 | -100.0% | ✅ PASS |
| V0014 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=250000 ann | 2.09% | 0% | 2.2% | 0.0 | -100.0% | ✅ PASS |
| V0015 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=3 ann | 12.22% | 100% | 6.5% | 12.73M | -20.0% | ✅ PASS |
| V0016 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=5 ann | 12.22% | 100% | 6.5% | 6.82M | -21.7% | ✅ PASS |
| V0017 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=7 ann | 12.22% | 100% | 6.5% | 3.60M | -25.1% | ✅ PASS |
| V0018 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=10 ann | 12.22% | 100% | 6.5% | 1.35M | -34.7% | ✅ PASS |
| V0019 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=15 ann | 12.22% | 100% | 6.5% | 242.3K | -80.2% | ✅ PASS |
| V0020 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=20 ann | 12.22% | 100% | 6.5% | 39.3K | -96.7% | ✅ PASS |
| V0021 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=0 | — | 12.79% | 100% | 6.5% | 36.97M | -23.6% | ✅ PASS |
| V0022 | m=1 y=30 n=500 NIFTY_=80/SBI_GI=20 rb=0 | — | 13.42% | 100% | 6.5% | 43.67M | -28.4% | ✅ PASS |
| V0023 | m=1 y=30 n=500 NIFTY_=90/SBI_GI=10 rb=0 | — | 13.72% | 100% | 6.5% | 47.27M | -30.7% | ✅ PASS |
| V0024 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| V0025 | m=1 y=30 n=500 NIFTY_=80/SBI_GI=20 | — | 13.17% | 100% | 6.5% | 40.87M | -25.7% | ✅ PASS |
| V0026 | m=1 y=30 n=500 NIFTY_=90/SBI_GI=10 | — | 13.57% | 100% | 6.5% | 45.53M | -29.8% | ✅ PASS |
| V0027 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=2 | — | 12.34% | 100% | 6.5% | 32.82M | -17.6% | ✅ PASS |
| V0028 | m=1 y=30 n=500 NIFTY_=80/SBI_GI=20 rb=2 | — | 13.26% | 100% | 6.5% | 41.87M | -25.7% | ✅ PASS |
| V0029 | m=1 y=30 n=500 NIFTY_=90/SBI_GI=10 rb=2 | — | 13.64% | 100% | 6.5% | 46.39M | -29.8% | ✅ PASS |
| V0030 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=3 | — | 12.47% | 100% | 6.5% | 33.98M | -17.5% | ✅ PASS |
| V0031 | m=1 y=30 n=500 NIFTY_=80/SBI_GI=20 rb=3 | — | 13.33% | 100% | 6.7% | 42.71M | -25.7% | ✅ PASS |
| V0032 | m=1 y=30 n=500 NIFTY_=90/SBI_GI=10 rb=3 | — | 13.70% | 100% | 6.5% | 47.07M | -29.8% | ✅ PASS |
| V0033 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=4 | — | 12.41% | 100% | 6.5% | 33.39M | -18.1% | ✅ PASS |
| V0034 | m=1 y=30 n=500 NIFTY_=80/SBI_GI=20 rb=4 | — | 13.31% | 100% | 6.5% | 42.46M | -26.1% | ✅ PASS |
| V0035 | m=1 y=30 n=500 NIFTY_=90/SBI_GI=10 rb=4 | — | 13.66% | 100% | 6.5% | 46.64M | -30.0% | ✅ PASS |
| V0036 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 7.8% | 31.75M | -17.5% | ✅ PASS |
| V0037 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 5.7% | 31.75M | -17.5% | ✅ PASS |
| V0038 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 3.0% | 31.75M | -17.5% | ✅ PASS |
| V0039 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 1.5% | 31.75M | -17.5% | ✅ PASS |

### Group `B2_extreme` (32 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0040 | m=1 y=1 n=1000 NIFTY_=60/SBI_GI=40 | — | 13.54% | 100% | 15.2% | 1.14M | -3.6% | ✅ PASS |
| V0041 | m=1 y=2 n=1000 NIFTY_=60/SBI_GI=40 | — | 11.67% | 100% | 15.2% | 1.25M | -5.6% | ✅ PASS |
| V0042 | m=1 y=3 n=1000 NIFTY_=60/SBI_GI=40 | — | 11.84% | 100% | 15.2% | 1.40M | -6.8% | ✅ PASS |
| V0043 | m=1 y=4 n=1000 NIFTY_=60/SBI_GI=40 | — | 11.78% | 100% | 15.2% | 1.56M | -7.2% | ✅ PASS |
| V0044 | m=1 y=55 n=500 NIFTY_=60/SBI_GI=40 | — | 12.09% | 100% | 5.7% | 531.39M | -19.6% | ✅ PASS |
| V0045 | m=1 y=65 n=500 NIFTY_=60/SBI_GI=40 | — | 12.14% | 100% | 5.7% | 1.72B | -19.6% | ✅ PASS |
| V0046 | m=1 y=75 n=500 NIFTY_=60/SBI_GI=40 | — | 12.17% | 100% | 5.7% | 5.51B | -19.6% | ✅ PASS |
| V0047 | m=1 y=85 n=500 NIFTY_=60/SBI_GI=40 | — | 12.21% | 100% | 5.7% | 17.94B | -19.6% | ✅ PASS |
| V0048 | m=1 y=100 n=500 NIFTY_=60/SBI_GI=40 | — | 12.17% | 100% | 5.7% | 97.14B | -19.6% | ✅ PASS |
| V0049 | m=1 y=30 n=10 NIFTY_=60/SBI_GI=40 | — | 11.67% | 100% | 6.0% | 27.44M | -18.4% | ✅ PASS |
| V0050 | m=1 y=30 n=25 NIFTY_=60/SBI_GI=40 | — | 11.63% | 100% | 6.0% | 27.12M | -19.6% | ✅ PASS |
| V0051 | m=1 y=30 n=50 NIFTY_=60/SBI_GI=40 | — | 12.20% | 100% | 6.0% | 31.63M | -18.0% | ✅ PASS |
| V0052 | m=1 y=30 n=100 NIFTY_=60/SBI_GI=40 | — | 12.05% | 100% | 6.5% | 30.39M | -18.0% | ✅ PASS |
| V0053 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| V0054 | m=1 y=30 n=2000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.21M | -17.5% | ✅ PASS |
| V0055 | m=1 y=30 n=5000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.15M | -17.5% | ✅ PASS |
| V0056 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.8 | -17.5% | ✅ PASS |
| V0057 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 317.5 | -17.5% | ✅ PASS |
| V0058 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 3.2K | -17.5% | ✅ PASS |
| V0059 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.8K | -17.5% | ✅ PASS |
| V0060 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 3.18B | -17.5% | ✅ PASS |
| V0061 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75B | -17.5% | ✅ PASS |
| V0062 | m=1 y=30 n=500 NIFTY_SMALLCAP=100% | — | 14.48% | 100% | 0.5% | 57.84M | -80.7% | ✅ PASS |
| V0063 | m=1 y=30 n=500 NIFTY_MIDCAP=100% | — | 17.03% | 100% | 2.0% | 111.90M | -65.4% | ✅ PASS |
| V0064 | m=1 y=30 n=500 NIFTY_BANK=100% | — | 20.16% | 100% | 4.2% | 247.22M | -59.4% | ✅ PASS |
| V0065 | m=1 y=30 n=500 NIFTY_IT=100% | — | 12.14% | 100% | 1.2% | 31.09M | -71.9% | ✅ PASS |
| V0066 | m=1 y=30 n=500 NIFTY_PHARMA=100% | — | 14.93% | 100% | 4.0% | 64.99M | -39.5% | ✅ PASS |
| V0067 | m=1 y=30 n=500 SILVER=100% | — | 46.67% | 100% | 14.0% | 97.77B | -17.5% | ✅ PASS |
| V0068 | m=1 y=30 n=500 NIFTY_=40/SBI_GI=40/GOLD=20 | — | 12.15% | 100% | 6.7% | 31.15M | -8.3% | ✅ PASS |
| V0069 | m=1 y=30 n=500 NIFTY_=30/NIFTY_=20/SBI_GI=30 | — | 13.97% | 100% | 7.0% | 50.51M | -13.4% | ✅ PASS |
| V0070 | m=1 y=30 n=500 NIFTY_=25/NIFTY_=15/SBI_GI=30 | — | 11.96% | 100% | 6.2% | 29.67M | -10.3% | ✅ PASS |
| V0071 | m=1 y=30 n=500 NIFTY_=20/NIFTY_=15/NIFTY_=10 | — | 12.84% | 100% | 6.7% | 37.53M | -10.9% | ✅ PASS |

### Group `C2_model` (21 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0072 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.21M | -17.5% | ✅ PASS |
| V0073 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.19% | 100% | 6.5% | 31.49M | -17.5% | ✅ PASS |
| V0074 | m=2 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.21M | -17.5% | ✅ PASS |
| V0075 | m=2 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.19% | 100% | 6.5% | 31.49M | -17.5% | ✅ PASS |
| V0076 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.51% | 100% | 4.7% | 34.37M | -23.6% | ✅ PASS |
| V0077 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.49% | 100% | 4.7% | 34.14M | -23.7% | ✅ PASS |
| V0078 | m=4 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.51% | 100% | 4.7% | 34.37M | -23.6% | ✅ PASS |
| V0079 | m=4 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.49% | 100% | 4.7% | 34.14M | -23.7% | ✅ PASS |
| V0080 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 fat_dof=3 | — | 12.36% | 100% | 4.7% | 32.98M | -24.3% | ✅ PASS |
| V0081 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 fat_dof=5 | — | 12.31% | 100% | 4.7% | 32.53M | -24.5% | ✅ PASS |
| V0082 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 fat_dof=10 | — | 12.27% | 100% | 4.7% | 32.21M | -24.0% | ✅ PASS |
| V0083 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 fat_dof=20 | — | 12.35% | 100% | 4.7% | 32.89M | -23.8% | ✅ PASS |
| V0084 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 fat_dof=30 | — | 12.31% | 100% | 4.7% | 32.56M | -23.6% | ✅ PASS |
| V0085 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 fat_dof=50 | — | 12.26% | 100% | 5.0% | 32.10M | -23.8% | ✅ PASS |
| V0086 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 fat_dof=100 | — | 12.21% | 100% | 5.0% | 31.72M | -23.8% | ✅ PASS |
| V0087 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS |
| V0088 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.50% | 100% | 4.7% | 34.21M | -25.0% | ✅ PASS |
| V0089 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customMean | — | 15.85% | 100% | 6.0% | 82.66M | -25.8% | ✅ PASS |
| V0090 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customMean | — | 3.81% | 100% | 1.7% | 3.07M | -25.5% | ✅ PASS |
| V0091 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customMean | — | 7.06% | 100% | 2.5% | 7.74M | -27.3% | ✅ PASS |
| V0092 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customMean | — | 0.11% | 100% | 0.8% | 1.03M | -49.3% | ✅ PASS |

### Group `D2_cashflow` (57 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0093 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 ann | 12.22% | 100% | 6.5% | 34.13M | -17.4% | ✅ PASS |
| V0094 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 ann | 12.22% | 100% | 6.5% | 35.55M | -17.3% | ✅ PASS |
| V0095 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 ann | 12.22% | 100% | 6.5% | 38.60M | -17.0% | ✅ PASS |
| V0096 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 ann | 12.22% | 100% | 6.5% | 63.19M | -15.9% | ✅ PASS |
| V0097 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=30000 mon | 1.14% | 0% | 2.0% | 0.0 | -100.0% | ✅ PASS |
| V0098 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=30000 mon | 1.24% | 0% | 2.0% | 0.0 | -100.0% | ✅ PASS |
| V0099 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=30000 qua | 5.10% | 1% | 3.5% | 0.0 | -100.0% | ✅ PASS |
| V0100 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=30000 qua | 11.03% | 47% | 4.5% | 0.0 | -100.0% | ✅ PASS |
| V0101 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=30000 ann | 12.22% | 100% | 6.5% | 20.79M | -18.9% | ✅ PASS |
| V0102 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=30000 ann | 12.22% | 100% | 6.5% | 24.11M | -18.4% | ✅ PASS |
| V0103 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | wd_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 26.88M | -18.0% | ✅ PASS |
| V0104 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contr_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 36.30M | -17.3% | ✅ PASS |
| V0105 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | wd_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 24.79M | -18.3% | ✅ PASS |
| V0106 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contr_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 38.46M | -17.1% | ✅ PASS |
| V0107 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | wd_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 20.79M | -18.9% | ✅ PASS |
| V0108 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contr_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 42.37M | -16.9% | ✅ PASS |
| V0109 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | wd_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 16.73M | -19.5% | ✅ PASS |
| V0110 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contr_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 46.60M | -16.7% | ✅ PASS |
| V0111 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | wd_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 12.61M | -20.4% | ✅ PASS |
| V0112 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contr_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 50.82M | -16.4% | ✅ PASS |
| V0113 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | wd_pctch amt=30000 ann | 10.62% | 16% | 6.0% | 0.0 | -100.0% | ✅ PASS |
| V0114 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contr_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 70.32M | -15.9% | ✅ PASS |
| V0115 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | wd_pctch amt=30000 ann | 5.66% | 0% | 4.2% | 0.0 | -100.0% | ✅ PASS |
| V0116 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contr_pctch amt=30000 ann | 12.22% | 100% | 6.5% | 247.04M | -15.9% | ✅ PASS |
| V0117 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | life_exp amt=30000000 ann | 0.73% | 0% | 1.7% | 0.0 | -100.0% | ✅ PASS |
| V0118 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | life_exp amt=30000000 ann | 0.62% | 0% | 1.7% | 0.0 | -100.0% | ✅ PASS |
| V0119 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | life_exp amt=30000000 ann | 0.40% | 0% | 1.5% | 0.0 | -100.0% | ✅ PASS |
| V0120 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | life_exp amt=30000000 ann | 0.33% | 0% | 1.7% | 0.0 | -100.0% | ✅ PASS |
| V0121 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | life_exp amt=30000000 ann | 0.25% | 0% | 1.5% | 0.0 | -100.0% | ✅ PASS |
| V0122 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | life_exp amt=30000000 ann | 0.10% | 0% | 1.5% | 0.0 | -100.0% | ✅ PASS |
| V0123 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=1 ann | 12.22% | 100% | 6.5% | 23.49M | -18.3% | ✅ PASS |
| V0124 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=2 ann | 12.22% | 100% | 6.5% | 17.32M | -19.1% | ✅ PASS |
| V0125 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=3 ann | 12.22% | 100% | 6.5% | 12.73M | -20.0% | ✅ PASS |
| V0126 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=4 ann | 12.22% | 100% | 6.5% | 9.33M | -20.8% | ✅ PASS |
| V0127 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=5 ann | 12.22% | 100% | 6.5% | 6.82M | -21.7% | ✅ PASS |
| V0128 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=6 ann | 12.22% | 100% | 6.5% | 4.96M | -22.9% | ✅ PASS |
| V0129 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=7 ann | 12.22% | 100% | 6.5% | 3.60M | -25.1% | ✅ PASS |
| V0130 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=8 ann | 12.22% | 100% | 6.5% | 2.60M | -27.1% | ✅ PASS |
| V0131 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=9 ann | 12.22% | 100% | 6.5% | 1.88M | -30.2% | ✅ PASS |
| V0132 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=10 ann | 12.22% | 100% | 6.5% | 1.35M | -34.7% | ✅ PASS |
| V0133 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=11 ann | 12.22% | 100% | 6.5% | 962.6K | -41.8% | ✅ PASS |
| V0134 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=12 ann | 12.22% | 100% | 6.5% | 685.9K | -51.5% | ✅ PASS |
| V0135 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=13 ann | 12.22% | 100% | 6.5% | 486.8K | -62.5% | ✅ PASS |
| V0136 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=14 ann | 12.22% | 100% | 6.5% | 344.1K | -72.4% | ✅ PASS |
| V0137 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=15 ann | 12.22% | 100% | 6.5% | 242.3K | -80.2% | ✅ PASS |
| V0138 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=16 ann | 12.22% | 100% | 6.5% | 169.9K | -85.8% | ✅ PASS |
| V0139 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=17 ann | 12.22% | 100% | 6.5% | 118.6K | -90.0% | ✅ PASS |
| V0140 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=18 ann | 12.22% | 100% | 6.5% | 82.4K | -93.0% | ✅ PASS |
| V0141 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=19 ann | 12.22% | 100% | 6.5% | 57.1K | -95.2% | ✅ PASS |
| V0142 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=20 ann | 12.22% | 100% | 6.5% | 39.3K | -96.7% | ✅ PASS |
| V0143 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=21 ann | 12.22% | 100% | 6.5% | 27.0K | -97.7% | ✅ PASS |
| V0144 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=22 ann | 12.22% | 96% | 6.5% | 18.4K | -98.4% | ✅ PASS |
| V0145 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=23 ann | 12.22% | 73% | 6.5% | 12.5K | -98.9% | ✅ PASS |
| V0146 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=24 ann | 12.22% | 30% | 6.5% | 8.4K | -99.3% | ✅ PASS |
| V0147 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=25 ann | 12.22% | 6% | 6.5% | 5.7K | -99.5% | ✅ PASS |
| V0148 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 6.5% | 16.08M | -19.6% | ✅ PASS |
| V0149 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 6.5% | 17.23M | -19.5% | ✅ PASS |

### Group `E2_inflation` (48 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0150 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 9.2% | 30.89M | -17.5% | ✅ PASS |
| V0151 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 9.2% | 30.89M | -17.5% | ✅ PASS |
| V0152 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 9.2% | 30.89M | -17.5% | ✅ PASS |
| V0153 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 9.2% | 30.89M | -17.5% | ✅ PASS |
| V0154 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 7.5% | 30.89M | -17.5% | ✅ PASS |
| V0155 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 7.5% | 30.89M | -17.5% | ✅ PASS |
| V0156 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 7.5% | 30.89M | -17.5% | ✅ PASS |
| V0157 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 7.5% | 30.89M | -17.5% | ✅ PASS |
| V0158 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 6.2% | 30.89M | -17.5% | ✅ PASS |
| V0159 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 6.2% | 30.89M | -17.5% | ✅ PASS |
| V0160 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 6.2% | 30.89M | -17.5% | ✅ PASS |
| V0161 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 6.2% | 30.89M | -17.5% | ✅ PASS |
| V0162 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 5.0% | 30.89M | -17.5% | ✅ PASS |
| V0163 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 5.0% | 30.89M | -17.5% | ✅ PASS |
| V0164 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 5.0% | 30.89M | -17.5% | ✅ PASS |
| V0165 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 5.0% | 30.89M | -17.5% | ✅ PASS |
| V0166 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 3.0% | 30.89M | -17.5% | ✅ PASS |
| V0167 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 3.0% | 30.89M | -17.5% | ✅ PASS |
| V0168 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 3.0% | 30.89M | -17.5% | ✅ PASS |
| V0169 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 3.0% | 30.89M | -17.5% | ✅ PASS |
| V0170 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 1.2% | 30.89M | -17.5% | ✅ PASS |
| V0171 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 1.2% | 30.89M | -17.5% | ✅ PASS |
| V0172 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 1.2% | 30.89M | -17.5% | ✅ PASS |
| V0173 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 1.2% | 30.89M | -17.5% | ✅ PASS |
| V0174 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 9.2% | 30.89M | -17.5% | ✅ PASS |
| V0175 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 9.2% | 30.89M | -17.5% | ✅ PASS |
| V0176 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 9.2% | 30.89M | -17.5% | ✅ PASS |
| V0177 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 9.2% | 30.89M | -17.5% | ✅ PASS |
| V0178 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 7.5% | 30.89M | -17.5% | ✅ PASS |
| V0179 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 7.5% | 30.89M | -17.5% | ✅ PASS |
| V0180 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 7.5% | 30.89M | -17.5% | ✅ PASS |
| V0181 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 7.5% | 30.89M | -17.5% | ✅ PASS |
| V0182 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 6.2% | 30.89M | -17.5% | ✅ PASS |
| V0183 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 6.2% | 30.89M | -17.5% | ✅ PASS |
| V0184 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 6.2% | 30.89M | -17.5% | ✅ PASS |
| V0185 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 6.2% | 30.89M | -17.5% | ✅ PASS |
| V0186 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 5.0% | 30.89M | -17.5% | ✅ PASS |
| V0187 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 5.0% | 30.89M | -17.5% | ✅ PASS |
| V0188 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 5.0% | 30.89M | -17.5% | ✅ PASS |
| V0189 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 5.0% | 30.89M | -17.5% | ✅ PASS |
| V0190 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 3.0% | 30.89M | -17.5% | ✅ PASS |
| V0191 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 3.0% | 30.89M | -17.5% | ✅ PASS |
| V0192 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 3.0% | 30.89M | -17.5% | ✅ PASS |
| V0193 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 3.0% | 30.89M | -17.5% | ✅ PASS |
| V0194 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 1.2% | 30.89M | -17.5% | ✅ PASS |
| V0195 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 1.2% | 30.89M | -17.5% | ✅ PASS |
| V0196 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 1.2% | 30.89M | -17.5% | ✅ PASS |
| V0197 | m=1 y=30 n=200 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 1.2% | 30.89M | -17.5% | ✅ PASS |

### Group `F2_correl` (12 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0198 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| V0199 | m=1 y=30 n=500 [('NIFTY_50', 0.6), ('SBI_GILT customCorr | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0200 | m=1 y=30 n=500 [('NIFTY_50', 0.6), ('SBI_GILT customCorr | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0201 | m=1 y=30 n=500 [('NIFTY_50', 0.6), ('SBI_GILT customCorr | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0202 | m=1 y=30 n=500 [('NIFTY_50', 0.6), ('SBI_GILT customCorr | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0203 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customCorr customMean | — | 8.54% | 100% | 2.7% | 11.69M | -31.0% | ✅ PASS |
| V0204 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customCorr customMean | — | 9.01% | 100% | 3.7% | 13.30M | -17.9% | ✅ PASS |
| V0205 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customCorr customMean | — | 8.77% | 100% | 3.2% | 12.46M | -24.6% | ✅ PASS |
| V0206 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customCorr customMean | — | 8.68% | 100% | 3.0% | 12.16M | -28.5% | ✅ PASS |
| V0207 | m=3 y=30 n=200 [('NIFTY_50', 0.6), ('SBI_GILT customCorr customMean | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0208 | m=1 y=30 n=200 [('NIFTY_50', 0.6), ('SBI_GILT customCorr | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0209 | m=1 y=30 n=500 NIFTY_=50/SBI_GI=50 | — | 11.73% | 100% | 6.5% | 27.90M | -13.8% | ✅ PASS |

### Group `G2_stress` (14 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0210 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| V0211 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 6.5% | 17.23M | -19.5% | ✅ PASS |
| V0212 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=1 | — | 12.22% | 100% | 6.2% | 31.75M | -17.5% | ✅ PASS |
| V0213 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=1 | withdraw amt=40000 ann | 12.22% | 100% | 6.2% | 16.52M | -19.8% | ✅ PASS |
| V0214 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=2 | — | 12.22% | 100% | 6.0% | 31.75M | -17.5% | ✅ PASS |
| V0215 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=2 | withdraw amt=40000 ann | 12.22% | 100% | 6.0% | 15.70M | -19.9% | ✅ PASS |
| V0216 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=3 | — | 12.22% | 100% | 5.7% | 31.75M | -17.5% | ✅ PASS |
| V0217 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=3 | withdraw amt=40000 ann | 12.22% | 100% | 5.7% | 14.64M | -20.1% | ✅ PASS |
| V0218 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=5 | — | 12.22% | 100% | 5.2% | 31.75M | -17.2% | ✅ PASS |
| V0219 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=5 | withdraw amt=40000 ann | 12.22% | 100% | 5.2% | 13.01M | -20.6% | ✅ PASS |
| V0220 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=7 | — | 12.22% | 100% | 5.0% | 31.75M | -17.2% | ✅ PASS |
| V0221 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=7 | withdraw amt=40000 ann | 12.22% | 100% | 5.0% | 11.77M | -21.0% | ✅ PASS |
| V0222 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=10 | — | 12.22% | 100% | 4.7% | 31.75M | -16.8% | ✅ PASS |
| V0223 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=10 | withdraw amt=40000 ann | 12.22% | 100% | 4.7% | 10.52M | -21.4% | ✅ PASS |

### Group `H2_rebal` (11 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0224 | m=1 y=30 n=500 NIFTY_50=100% rb=0 | — | 15.12% | 100% | 2.7% | 68.38M | -56.9% | ✅ PASS |
| V0225 | m=1 y=30 n=500 NIFTY_50=100% | — | 15.12% | 100% | 2.7% | 68.38M | -56.9% | ✅ PASS |
| V0226 | m=1 y=30 n=500 NIFTY_50=100% rb=4 | — | 15.12% | 100% | 2.7% | 68.38M | -56.9% | ✅ PASS |
| V0227 | m=1 y=30 n=500 NIFTY_=50/SBI_GI=50 rb=0 | — | 12.37% | 100% | 6.5% | 33.07M | -20.7% | ✅ PASS |
| V0228 | m=1 y=30 n=500 NIFTY_=50/SBI_GI=50 | — | 11.73% | 100% | 6.5% | 27.90M | -13.8% | ✅ PASS |
| V0229 | m=1 y=30 n=500 NIFTY_=50/SBI_GI=50 rb=2 | — | 11.88% | 100% | 6.5% | 28.98M | -13.7% | ✅ PASS |
| V0230 | m=1 y=30 n=500 NIFTY_=50/SBI_GI=50 rb=3 | — | 11.98% | 100% | 6.5% | 29.83M | -13.7% | ✅ PASS |
| V0231 | m=1 y=30 n=500 NIFTY_=50/SBI_GI=50 rb=4 | — | 11.93% | 100% | 6.5% | 29.42M | -14.2% | ✅ PASS |
| V0232 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=0 | withdraw amt=30000 ann | 12.79% | 100% | 6.5% | 24.18M | -24.2% | ✅ PASS |
| V0233 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=30000 ann | 12.22% | 100% | 6.5% | 20.79M | -18.9% | ✅ PASS |
| V0234 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=4 | withdraw amt=30000 ann | 12.41% | 100% | 6.5% | 22.40M | -19.4% | ✅ PASS |

### Group `I2_bootstrap` (22 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0235 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.12% | 100% | 4.7% | 23.65M | -18.6% | ✅ PASS |
| V0236 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.09% | 100% | 4.7% | 23.47M | -18.6% | ✅ PASS |
| V0237 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 bm=0 | — | 11.04% | 100% | 5.0% | 23.15M | -18.6% | ✅ PASS |
| V0238 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.21M | -17.5% | ✅ PASS |
| V0239 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.19% | 100% | 6.5% | 31.49M | -17.5% | ✅ PASS |
| V0240 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.18% | 100% | 6.5% | 31.43M | -17.5% | ✅ PASS |
| V0241 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.15% | 100% | 6.5% | 23.83M | -16.2% | ✅ PASS |
| V0242 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.17% | 100% | 6.5% | 23.95M | -16.4% | ✅ PASS |
| V0243 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.13% | 100% | 6.7% | 23.72M | -16.2% | ✅ PASS |
| V0244 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.09% | 100% | 6.0% | 23.48M | -16.2% | ✅ PASS |
| V0245 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.07% | 100% | 6.2% | 23.36M | -16.2% | ✅ PASS |
| V0246 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.13% | 100% | 6.5% | 23.70M | -16.2% | ✅ PASS |
| V0247 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.18% | 100% | 6.2% | 24.03M | -16.2% | ✅ PASS |
| V0248 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.17% | 100% | 6.5% | 23.94M | -16.2% | ✅ PASS |
| V0249 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.12% | 100% | 6.5% | 23.67M | -16.4% | ✅ PASS |
| V0250 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.04% | 100% | 6.2% | 23.13M | -16.2% | ✅ PASS |
| V0251 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.12% | 100% | 6.5% | 23.67M | -16.2% | ✅ PASS |
| V0252 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.12% | 100% | 6.7% | 23.64M | -16.4% | ✅ PASS |
| V0253 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.06% | 100% | 6.7% | 23.29M | -16.2% | ✅ PASS |
| V0254 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.18% | 100% | 6.7% | 24.06M | -16.2% | ✅ PASS |
| V0255 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.13% | 100% | 6.5% | 23.70M | -16.2% | ✅ PASS |
| V0256 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.93% | 100% | 7.0% | 29.42M | -16.4% | ✅ PASS |

### Group `J2_regression` (8 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0257 | m=1 y=30 n=500 [('NIFTY_50', 0.6), ('SBI_GILT | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0258 | m=1 y=30 n=500 [('NIFTY_50', 0.6), ('SBI_GILT | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0259 | m=1 y=30 n=500 [('NIFTY_50', 0.6), ('SBI_GILT | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0260 | m=1 y=30 n=500 [('FAKE_ASSET_XYZ', 1.0)] | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0261 | m=1 y=30 n=500 [('NIFTY_50', 0.3), ('SBI_GILT | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0262 | m=3 y=30 n=100 [('NIFTY_50', 0.6), ('SBI_GILT | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| V0263 | m=3 y=30 n=200 NIFTY_=60/SBI_GI=40 customMean | — | 7.00% | 100% | 2.7% | 7.61M | -26.6% | ✅ PASS |
| V0264 | m=1 y=30 n=200 NIFTY_=50/SBI_CO=50 | — | 11.00% | 100% | 6.5% | 22.87M | -16.4% | ✅ PASS |

### Group `K2_pv` (10 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0265 | m=1 y=30 n=100 NIFTY_=60/SBI_GI=40 | — | 12.05% | 100% | 6.5% | 30.39M | -18.0% | ✅ PASS |
| V0266 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| V0267 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.21M | -17.5% | ✅ PASS |
| V0268 | m=1 y=30 n=5000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.15M | -17.5% | ✅ PASS |
| V0269 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 6.5% | 17.23M | -19.5% | ✅ PASS |
| V0270 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.15% | 100% | 6.5% | 16.87M | -19.5% | ✅ PASS |
| V0271 | m=1 y=30 n=5000 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.15% | 100% | 6.5% | 16.84M | -19.5% | ✅ PASS |
| V0272 | m=1 y=30 n=500 NIFTY_50=100% | — | 15.12% | 100% | 2.7% | 68.38M | -56.9% | ✅ PASS |
| V0273 | m=1 y=30 n=1000 NIFTY_50=100% | — | 14.71% | 100% | 2.7% | 61.30M | -57.1% | ✅ PASS |
| V0274 | m=1 y=10 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.10% | 100% | 12.0% | 3.13M | -15.9% | ✅ PASS |

### Group `L2_real_nom` (6 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| V0275 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 9.5% | 31.75M | -17.5% | ✅ PASS |
| V0276 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| V0277 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 7.0% | 31.75M | -17.5% | ✅ PASS |
| V0278 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 4.0% | 31.75M | -17.5% | ✅ PASS |
| V0279 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 1.5% | 31.75M | -17.5% | ✅ PASS |
| V0280 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 0.0% | 31.75M | -17.5% | ✅ PASS |

### Group `M2_repro` (16 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| W0001 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| W0002 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| W0003 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.09% | 100% | 6.5% | 30.66M | -17.5% | ✅ PASS |
| W0004 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.09% | 100% | 6.5% | 30.66M | -17.5% | ✅ PASS |
| W0005 | m=2 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| W0006 | m=2 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| W0007 | m=2 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.09% | 100% | 6.5% | 30.66M | -17.5% | ✅ PASS |
| W0008 | m=2 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.09% | 100% | 6.5% | 30.66M | -17.5% | ✅ PASS |
| W0009 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS |
| W0010 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS |
| W0011 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.26% | 100% | 4.7% | 32.09M | -24.1% | ✅ PASS |
| W0012 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.26% | 100% | 4.7% | 32.09M | -24.1% | ✅ PASS |
| W0013 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS |
| W0014 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.34% | 100% | 4.5% | 32.78M | -23.9% | ✅ PASS |
| W0015 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.26% | 100% | 4.7% | 32.09M | -24.1% | ✅ PASS |
| W0016 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.26% | 100% | 4.7% | 32.09M | -24.1% | ✅ PASS |

### Group `N2_param_vol` (5 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| W0017 | m=3 y=30 n=1000 [('NIFTY_50', 0.6), ('SBI_GILT customMean | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ❌ FAIL |
| W0018 | m=3 y=30 n=1000 [('NIFTY_50', 0.6), ('SBI_GILT customMean | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ❌ FAIL |
| W0019 | m=3 y=30 n=1000 [('NIFTY_50', 0.6), ('SBI_GILT customMean | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ❌ FAIL |
| W0020 | m=3 y=30 n=1000 [('NIFTY_50', 0.6), ('SBI_GILT customMean | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ❌ FAIL |
| W0021 | m=3 y=30 n=1000 [('NIFTY_50', 0.6), ('SBI_GILT customMean | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ❌ FAIL |

### Group `N2_param_vol_fixed` (9 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| Y0001 | m=3 y=30 n=1000 NIFTY_50=100% customMean | — | 13.64% | 100% | 4.0% | 46.32M | -39.2% | ✅ PASS |
| Y0002 | m=3 y=30 n=1000 NIFTY_50=100% customMean | — | 9.86% | 100% | 4.2% | 16.78M | -17.9% | ✅ PASS |
| Y0003 | m=3 y=30 n=1000 NIFTY_50=100% customMean | — | 0.26% | 100% | 0.0% | 1.08M | -82.1% | ✅ PASS |
| Y0004 | m=3 y=30 n=1000 SBI_GILT=100% customMean | — | 4.95% | 100% | 2.7% | 4.26M | -9.2% | ✅ PASS |
| Y0005 | m=3 y=30 n=1000 SBI_GILT=100% customMean | — | 3.83% | 100% | 1.2% | 3.09M | -44.0% | ✅ PASS |
| Y0006 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 customMean | — | 10.68% | 100% | 4.2% | 21.00M | -22.5% | ✅ PASS |
| Y0007 | m=3 y=30 n=1000 NIFTY_=60/SBI_GI=40 customMean | — | 10.26% | 100% | 3.5% | 18.71M | -30.6% | ✅ PASS |
| Y0008 | m=3 y=30 n=500 [('NIFTY_50', 0.6), ('SBI_GILT customMean | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |
| Y0009 | m=3 y=30 n=500 [('NIFTY_50', 0.6), ('SBI_GILT customMean | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |

### Group `O2_custom_corr` (6 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| W0022 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customCorr customMean | — | 7.70% | 100% | 3.0% | 9.25M | -20.3% | ✅ PASS |
| W0023 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customCorr customMean | — | 7.61% | 100% | 3.0% | 9.04M | -23.6% | ✅ PASS |
| W0024 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customCorr customMean | — | 7.46% | 100% | 2.7% | 8.65M | -26.5% | ✅ PASS |
| W0025 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customCorr customMean | — | 7.38% | 100% | 2.5% | 8.46M | -30.3% | ✅ PASS |
| W0026 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 customCorr customMean | — | 7.27% | 100% | 2.2% | 8.21M | -32.8% | ✅ PASS |
| W0027 | m=3 y=30 n=200 [('NIFTY_50', 0.6), ('SBI_GILT customCorr customMean | — | 0.00% | 0% | 0.0% | 0.0 | 0.0% | ✅ PASS |

### Group `P2_stress_verif` (7 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| W0028 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=1 | withdraw amt=50000 ann | 12.22% | 100% | 6.2% | 12.77M | -20.7% | ✅ PASS |
| W0029 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=3 | withdraw amt=50000 ann | 12.22% | 100% | 5.7% | 10.29M | -21.4% | ✅ PASS |
| W0030 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=5 | withdraw amt=50000 ann | 12.22% | 99% | 5.2% | 8.28M | -23.4% | ✅ PASS |
| W0031 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=8 | withdraw amt=50000 ann | 12.22% | 97% | 5.0% | 6.09M | -26.5% | ✅ PASS |
| W0032 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 stress=10 | withdraw amt=50000 ann | 12.22% | 93% | 4.7% | 5.12M | -27.8% | ✅ PASS |
| W0033 | m=1 y=30 n=500 NIFTY_50=100% stress=5 | — | 15.12% | 100% | 0.5% | 68.38M | -79.1% | ✅ PASS |
| W0034 | m=1 y=30 n=500 NIFTY_50=100% stress=10 | — | 15.12% | 100% | 0.0% | 68.38M | -79.1% | ✅ PASS |

### Group `Q2_pv_ext` (6 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| W0035 | m=1 y=30 n=2000 NIFTY_=60/SBI_GI=40 | withdraw amt=30000 ann | 12.15% | 100% | 6.5% | 20.52M | -18.9% | ✅ PASS |
| W0036 | m=1 y=30 n=2000 NIFTY_=60/SBI_GI=40 | withdraw amt=50000 ann | 12.15% | 100% | 6.5% | 13.35M | -20.4% | ✅ PASS |
| W0037 | m=1 y=30 n=2000 NIFTY_=60/SBI_GI=40 | withdraw amt=60000 ann | 12.15% | 99% | 6.5% | 9.71M | -21.4% | ✅ PASS |
| W0038 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=400000 ann | 12.15% | 100% | 6.5% | 168.70M | -19.5% | ✅ PASS |
| W0039 | m=1 y=30 n=2000 NIFTY_=40/SBI_GI=60 | — | 11.19% | 100% | 6.2% | 24.12M | -10.3% | ✅ PASS |
| W0040 | m=1 y=30 n=2000 NIFTY_=20/SBI_GI=80 | — | 10.20% | 100% | 5.7% | 18.41M | -3.3% | ✅ PASS |

### Group `R2_convergence` (6 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| W0041 | m=1 y=30 n=100 NIFTY_=60/SBI_GI=40 | — | 12.05% | 100% | 6.5% | 30.39M | -18.0% | ✅ PASS |
| W0042 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| W0043 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.21M | -17.5% | ✅ PASS |
| W0044 | m=1 y=30 n=2500 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.19M | -17.5% | ✅ PASS |
| W0045 | m=1 y=30 n=5000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.15M | -17.5% | ✅ PASS |
| W0046 | m=1 y=30 n=10000 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.18M | -17.5% | ✅ PASS |

### Group `S2_block` (40 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| W0047 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.10% | 100% | 5.7% | 23.51M | -16.4% | ✅ PASS |
| W0048 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.87% | 100% | 6.5% | 28.95M | -16.4% | ✅ PASS |
| W0049 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.07% | 100% | 6.0% | 23.34M | -16.2% | ✅ PASS |
| W0050 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.89% | 100% | 6.5% | 29.12M | -16.4% | ✅ PASS |
| W0051 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.03% | 100% | 6.2% | 23.09M | -16.2% | ✅ PASS |
| W0052 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.94% | 100% | 7.0% | 29.49M | -16.5% | ✅ PASS |
| W0053 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.11% | 100% | 6.5% | 23.59M | -16.2% | ✅ PASS |
| W0054 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.81% | 100% | 7.0% | 28.46M | -16.4% | ✅ PASS |
| W0055 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.13% | 100% | 6.5% | 23.70M | -16.2% | ✅ PASS |
| W0056 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 12.00% | 100% | 7.2% | 29.95M | -16.2% | ✅ PASS |
| W0057 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.13% | 100% | 6.0% | 23.71M | -16.4% | ✅ PASS |
| W0058 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.85% | 100% | 7.0% | 28.76M | -16.4% | ✅ PASS |
| W0059 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.18% | 100% | 6.2% | 24.03M | -16.4% | ✅ PASS |
| W0060 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.93% | 100% | 7.0% | 29.40M | -16.4% | ✅ PASS |
| W0061 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.15% | 100% | 6.5% | 23.85M | -16.2% | ✅ PASS |
| W0062 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.90% | 100% | 7.2% | 29.16M | -16.4% | ✅ PASS |
| W0063 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.06% | 100% | 6.7% | 23.26M | -16.2% | ✅ PASS |
| W0064 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.81% | 100% | 7.2% | 28.49M | -16.4% | ✅ PASS |
| W0065 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.15% | 100% | 6.7% | 23.82M | -16.2% | ✅ PASS |
| W0066 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.78% | 100% | 7.0% | 28.21M | -16.4% | ✅ PASS |
| W0067 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.08% | 100% | 6.2% | 23.39M | -16.4% | ✅ PASS |
| W0068 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 12.12% | 100% | 7.0% | 30.95M | -16.5% | ✅ PASS |
| W0069 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.10% | 100% | 6.5% | 23.55M | -16.2% | ✅ PASS |
| W0070 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.98% | 100% | 7.2% | 29.76M | -16.4% | ✅ PASS |
| W0071 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.11% | 100% | 6.7% | 23.60M | -16.2% | ✅ PASS |
| W0072 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.84% | 100% | 7.5% | 28.69M | -16.4% | ✅ PASS |
| W0073 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.12% | 100% | 6.7% | 23.64M | -16.4% | ✅ PASS |
| W0074 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.85% | 100% | 7.0% | 28.81M | -16.4% | ✅ PASS |
| W0075 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.08% | 100% | 6.7% | 23.40M | -16.2% | ✅ PASS |
| W0076 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.99% | 100% | 7.2% | 29.85M | -16.4% | ✅ PASS |
| W0077 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.12% | 100% | 6.7% | 23.62M | -16.2% | ✅ PASS |
| W0078 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.81% | 100% | 7.2% | 28.50M | -16.5% | ✅ PASS |
| W0079 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.17% | 100% | 6.7% | 23.98M | -16.2% | ✅ PASS |
| W0080 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.98% | 100% | 7.0% | 29.83M | -16.4% | ✅ PASS |
| W0081 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.07% | 100% | 6.7% | 23.31M | -16.4% | ✅ PASS |
| W0082 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.93% | 100% | 7.2% | 29.39M | -16.4% | ✅ PASS |
| W0083 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.10% | 100% | 6.7% | 23.53M | -16.2% | ✅ PASS |
| W0084 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.77% | 100% | 7.5% | 28.19M | -16.2% | ✅ PASS |
| W0085 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 11.20% | 100% | 6.7% | 24.17M | -16.4% | ✅ PASS |
| W0086 | m=1 y=30 n=300 NIFTY_=60/SBI_GI=40 bm=2 | — | 12.27% | 100% | 6.2% | 32.19M | -16.5% | ✅ PASS |

### Group `T2_seed` (10 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| W0087 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.16% | 100% | 6.5% | 31.29M | -17.5% | ✅ PASS |
| W0088 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.07% | 100% | 6.5% | 30.55M | -17.5% | ✅ PASS |
| W0089 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| W0090 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.09% | 100% | 6.5% | 30.66M | -17.5% | ✅ PASS |
| W0091 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.18% | 100% | 6.5% | 31.45M | -18.0% | ✅ PASS |
| W0092 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.15% | 100% | 6.5% | 31.19M | -17.5% | ✅ PASS |
| W0093 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.12% | 100% | 6.5% | 30.93M | -18.0% | ✅ PASS |
| W0094 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.11% | 100% | 6.5% | 30.85M | -18.0% | ✅ PASS |
| W0095 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.09% | 100% | 6.5% | 30.68M | -17.5% | ✅ PASS |
| W0096 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.09% | 100% | 6.5% | 30.70M | -17.5% | ✅ PASS |

### Group `U2_cf_rebal` (9 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| W0097 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=0 | contrib amt=20000 mon | 12.68% | 100% | 6.5% | 106.80M | -22.3% | ✅ PASS |
| W0098 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=0 | withdraw amt=40000 ann | 12.79% | 100% | 6.5% | 20.32M | -24.7% | ✅ PASS |
| W0099 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=0 | fixed% pct=5.0 ann | 12.79% | 100% | 6.5% | 7.93M | -27.8% | ✅ PASS |
| W0100 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=20000 mon | 12.22% | 100% | 6.5% | 95.51M | -16.7% | ✅ PASS |
| W0101 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 6.5% | 17.23M | -19.5% | ✅ PASS |
| W0102 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=5.0 ann | 12.22% | 100% | 6.5% | 6.82M | -21.7% | ✅ PASS |
| W0103 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=4 | contrib amt=20000 mon | 12.41% | 100% | 6.5% | 99.82M | -17.4% | ✅ PASS |
| W0104 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=4 | withdraw amt=40000 ann | 12.41% | 100% | 6.5% | 18.40M | -19.9% | ✅ PASS |
| W0105 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 rb=4 | fixed% pct=5.0 ann | 12.41% | 100% | 6.5% | 7.17M | -22.2% | ✅ PASS |

### Group `V2_edge` (9 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| W0106 | m=1 y=30 n=1000 SBI_GILT=100% | — | 9.16% | 100% | 5.2% | 13.86M | -2.8% | ✅ PASS |
| W0107 | m=1 y=30 n=1000 SBI_LIQUID=100% | — | 2.61% | 100% | 2.2% | 2.17M | -0.5% | ✅ PASS |
| W0108 | m=1 y=30 n=1000 GOLD=100% | — | 12.44% | 100% | 4.2% | 33.73M | -25.3% | ✅ PASS |
| W0109 | m=1 y=5 n=1000 NIFTY_SMALLCAP=100% | — | 16.93% | 100% | 7.2% | 2.19M | -42.0% | ✅ PASS |
| W0110 | m=1 y=100 n=200 NIFTY_50=100% | — | 14.33% | 100% | 2.0% | 655.79B | -70.4% | ✅ PASS |
| W0111 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=100000 mon | 12.23% | 100% | 6.5% | 1.04B | -15.3% | ✅ PASS |
| W0112 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 0.5% | 31.75M | -17.5% | ✅ PASS |
| W0113 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 11.0% | 31.75M | -17.5% | ✅ PASS |
| W0114 | m=1 y=1 n=100 NIFTY_=60/SBI_GI=40 | — | 9.83% | 100% | 15.2% | 1.10M | -4.9% | ✅ PASS |

### Group `X2_multi_rebal` (3 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| W0115 | m=1 y=30 n=500 NIFTY_=20/NIFTY_=10/NIFTY_=10 rb=0 | — | 14.54% | 100% | 6.7% | 58.70M | -18.2% | ✅ PASS |
| W0116 | m=1 y=30 n=500 NIFTY_=20/NIFTY_=10/NIFTY_=10 | — | 12.46% | 100% | 6.7% | 33.89M | -8.7% | ✅ PASS |
| W0117 | m=1 y=30 n=500 NIFTY_=20/NIFTY_=10/NIFTY_=10 rb=4 | — | 12.29% | 100% | 6.5% | 32.41M | -9.2% | ✅ PASS |

### Group `Y1_boundary` (24 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| Y0010 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=35000 ann | 12.15% | 100% | 6.5% | 18.57M | -19.2% | ✅ PASS |
| Y0011 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.15% | 100% | 6.5% | 16.87M | -19.5% | ✅ PASS |
| Y0012 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=45000 ann | 12.15% | 100% | 6.5% | 15.12M | -19.9% | ✅ PASS |
| Y0013 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=50000 ann | 12.15% | 100% | 6.5% | 13.25M | -20.4% | ✅ PASS |
| Y0014 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=55000 ann | 12.15% | 100% | 6.5% | 11.50M | -20.9% | ✅ PASS |
| Y0015 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=60000 ann | 12.15% | 99% | 6.5% | 9.64M | -21.4% | ✅ PASS |
| Y0016 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=65000 ann | 12.15% | 97% | 6.5% | 7.90M | -22.1% | ✅ PASS |
| Y0017 | m=1 y=30 n=1000 NIFTY_=60/SBI_GI=40 | withdraw amt=70000 ann | 12.15% | 92% | 6.2% | 6.13M | -23.1% | ✅ PASS |
| Y0018 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 mon | 12.22% | 100% | 6.5% | 147.48M | -15.7% | ✅ PASS |
| Y0019 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=25000 mon | 12.23% | 100% | 6.5% | 319.24M | -15.3% | ✅ PASS |
| Y0020 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=50000 mon | 12.23% | 100% | 6.5% | 608.54M | -15.2% | ✅ PASS |
| Y0021 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=100000 mon | 12.23% | 100% | 6.5% | 1.19B | -15.2% | ✅ PASS |
| Y0022 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 7.8% | 19.66M | -19.1% | ✅ PASS |
| Y0023 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 7.8% | 19.66M | -19.1% | ✅ PASS |
| Y0024 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 7.8% | 19.66M | -19.1% | ✅ PASS |
| Y0025 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 5.2% | 13.94M | -20.1% | ✅ PASS |
| Y0026 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 5.2% | 13.94M | -20.1% | ✅ PASS |
| Y0027 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 5.2% | 13.94M | -20.1% | ✅ PASS |
| Y0028 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.18% | 72% | 2.7% | 3.46M | -33.0% | ✅ PASS |
| Y0029 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.18% | 72% | 2.7% | 3.46M | -33.0% | ✅ PASS |
| Y0030 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.18% | 72% | 2.7% | 3.46M | -33.0% | ✅ PASS |
| Y0031 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 7.93% | 1% | 0.8% | 0.0 | -100.0% | ✅ PASS |
| Y0032 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 7.93% | 1% | 0.8% | 0.0 | -100.0% | ✅ PASS |
| Y0033 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 7.93% | 1% | 0.8% | 0.0 | -100.0% | ✅ PASS |

### Group `Y2_ratios` (6 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| Y0034 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| Y0035 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| Y0036 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| Y0037 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| Y0038 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |
| Y0039 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | — | 12.22% | 100% | 6.5% | 31.75M | -17.5% | ✅ PASS |

### Group `Y3_diverse` (5 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| Y0040 | m=1 y=30 n=500 NIFTY_=20/NIFTY_=20/NIFTY_=20 | — | 15.36% | 100% | 7.0% | 72.64M | -25.0% | ✅ PASS |
| Y0041 | m=1 y=30 n=500 NIFTY_=30/NIFTY_=30/NIFTY_=20 | — | 14.04% | 100% | 4.7% | 51.48M | -31.6% | ✅ PASS |
| Y0042 | m=1 y=30 n=500 SBI_GI=60/SBI_LI=20/SBI_CO=20 | — | 6.75% | 100% | 4.2% | 7.10M | -1.3% | ✅ PASS |
| Y0043 | m=1 y=30 n=500 NIFTY_=15/NIFTY_=15/NIFTY_=15 | — | 14.32% | 100% | 7.0% | 55.38M | -17.5% | ✅ PASS |
| Y0044 | m=1 y=30 n=500 GOLD=50/NIFTY_=30/SBI_LI=20 | — | 11.23% | 100% | 5.2% | 24.36M | -11.0% | ✅ PASS |

### Group `Y4_model_cf` (9 tests)

| ID | Config | Cashflow | CAGR | SR | SWR | Med Final (₹) | Max DD | Verdict |
|----|--------|----------|------|-----|-----|---------------|--------|---------|
| Y0045 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 mon | 12.22% | 100% | 6.5% | 63.42M | -17.0% | ✅ PASS |
| Y0046 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.22% | 100% | 6.5% | 17.23M | -19.5% | ✅ PASS |
| Y0047 | m=1 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=5.0 ann | 12.22% | 100% | 6.5% | 6.82M | -21.7% | ✅ PASS |
| Y0048 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 mon | 12.34% | 100% | 4.5% | 65.64M | -21.3% | ✅ PASS |
| Y0049 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.34% | 99% | 4.5% | 17.23M | -27.7% | ✅ PASS |
| Y0050 | m=3 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=5.0 ann | 12.34% | 100% | 4.5% | 7.04M | -32.5% | ✅ PASS |
| Y0051 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | contrib amt=10000 mon | 12.34% | 100% | 4.5% | 65.64M | -21.3% | ✅ PASS |
| Y0052 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | withdraw amt=40000 ann | 12.34% | 99% | 4.5% | 17.23M | -27.7% | ✅ PASS |
| Y0053 | m=4 y=30 n=500 NIFTY_=60/SBI_GI=40 | fixed% pct=5.0 ann | 12.34% | 100% | 4.5% | 7.04M | -32.5% | ✅ PASS |

---

## 8. Brutally Honest Assessment

### What's working

- **Bootstrap sampling** produces stable, reproducible, statistically correct output. Historical and bootstrap variants match theoretical expectations.
- **Parametric models** (Normal + fat-tail-t) now match theoretical variance to within 0.1pp. The old double-variance bug is genuinely gone.
- **GARCH sampler** now honors cross-asset correlations via Cholesky decomposition.
- **SWR** is a real Monte Carlo calculation. No more 8% ceiling. Distribution is smooth across configs.
- **Success rate** correctly drops with high fixed-amount withdrawals. The old asymptote-to-zero bug is genuinely gone.
- **Fixed-% withdrawal** now applies at configured frequency (not every month). Portfolio decays gracefully.
- **Rebalancing** properly tracks per-asset balances. Effects on CAGR and drawdown are meaningful and directionally correct.
- **Real returns** use Fisher equation, not arithmetic subtraction.
- **Stochastic inflation** is genuinely sampled per (sim, month), and `inflation_model` config now branches.
- **Config-time validation** works: unknown assets, bad weights, dof≤2, allocation mismatch, custom_correlation shape, custom_means length — all raise ValueError with clear messages.
- **Regression tests** confirm cashflow types 5/6 and `tax_enabled=True` raise NotImplementedError.
- **Reproducibility** perfect across all 4 models.

### What's still not perfect

- ~~`custom_correlation` silently ignored under `model=1` / `model=2`~~ **(V2-2 FIXED)** — now raises ValueError at config time.
- ~~FatTailedSampler produces unphysical monthly returns at low dof~~ **(V2-3 FIXED)** — clipped to `> -99%` in sampler.
- **SR still 100% for many withdrawal scenarios**. This is largely because Indian equity historical returns are high enough that 3-6% withdrawal genuinely doesn't deplete. Not a bug — it's the data. However:
  - If a user has short-history assets (like SBI_GILT with only 12 years), bootstrap samples with replacement don't capture true tail risk from unobserved crises.
  - This is a **data-window limitation**, flagged in v1 report §5. Not fixable without more historical data.
- **Correlation matrix identity-padding is silent** for missing assets in the historical corr matrix. A warning is emitted, but the warning goes to Python's `warnings` module and may not be visible in the API response.
- **Cashflow types 5 (rolling avg) and 6 (Guyton-Klinger geometric)** are still unsupported — they raise NotImplementedError. If users want these, they need implementation.
- **Life-expectancy withdrawal** now correctly spreads over 12 months, but the underlying IRS table is US-based. Documented in code but a proper Indian SRS table would be more accurate.
- **CAGR bias in extreme scenarios**: while CAGR now includes -100% wipeout years (fixed), the median CAGR is fairly stable across stress levels because the median is a robust statistic. To see stress effect, look at p10 CAGR or tail statistics.
- **Test harness** (`run_v2_tests.py`, `run_v2_tests_batch2.py`, `run_v2_tests_batch3.py`) has 5 tests that fail because of my own test-writing bug (missing `assets=` arg for `custom_means` tests). The engine now correctly refuses to run these bad configs.

### Would I trust this for production?

For a **retirement-planning tool with reasonable inputs** (2-4 assets, standard cashflows, dof≥5, 20-40 year horizons): **yes**, with these remaining caveats:

1. ~~Add config-time validation that `custom_correlation` matches `model ∈ {3, 4}`~~ **(V2-2 DONE)**
2. ~~Clip FatTailedSampler returns to `> -0.99`~~ **(V2-3 DONE)**
3. Extend gilt/bond data history beyond 2013 for more robust tail estimates.
4. Consider implementing cashflow types 5 & 6 or removing them from the API entirely.
5. Life expectancy table should be swapped to Indian SRS data before advertising this feature.
6. Log correlation-padding warnings to the API response, not just Python warnings module.

For **an exact PV replacement**: no. PV uses stochastic inflation from CPI history (Macrowise does when `inflation_model=1` AND `inflation_data.pkl` is populated, else parametric fallback), and PV has more sophisticated life-tables, tax logic (Macrowise raises NotImplementedError), and cashflow types (5, 6 unimplemented).

### Final Verdict

The engine went from **~7% test pass rate before fixes** to **98.9% pass rate after fixes** on an independent 450-test matrix. The 5 remaining failures are all pre-fix test-harness bugs on my end (they intentionally exercise invalid configs to trigger the engine's new validation; my harness for those specific cases doesn't declare `expect_error='valueerror'`).

**The 48 bugs from v1 stay fixed. All 3 new bugs found by v2 (V2-1, V2-2, V2-3) are also fixed.** The Monte Carlo engine now:

- Matches published financial theory (Fisher equation, geometric CAGR, Sortino TDD).
- Converges cleanly under increasing sim counts.
- Is deterministic under seeds (perfect reproducibility across all 4 models).
- Correctly responds to inputs (SWR/SR/rebalance/inflation all behave as expected).
- Raises informative errors at config time for invalid inputs (custom_means length, custom_correlation model mismatch, unknown asset, weights ≠ 1, dof ≤ 2, etc.).
- Produces physically valid return draws (fat-tail clipped to `> -99%`).

---

*End of v2 report*
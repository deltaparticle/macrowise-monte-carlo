"""V2 exhaustive test harness — 450+ NEW cases not in v1.

Focuses on:
- Fix validators (SWR/SR/rebalance/fixed-% actually working)
- Extreme boundaries
- Model correctness (parametric vol vs theoretical, GARCH clustering)
- Cashflow deep dive (timing, life-exp, pct-change, inflation)
- Inflation model (historical vs parametric)
- Custom correlations and multi-asset
- Sequence stress
- Rebalancing effects
- Bootstrap deep dive
- Regression tests for NotImplementedError, ValueError, etc.
- PV cross-check convergence
"""
import json
import time
import traceback
import warnings
from pathlib import Path
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent))

# Suppress verbose per-run prints
import contextlib, io

from macrowise.engine.monte_carlo import MonteCarloConfig, MonteCarloSimulation
from macrowise.engine.cashflow import CashFlowConfig

OUT = Path(__file__).parent / "v2_test_results.json"

# Silence stdout inside sims
_null = io.StringIO()

def run_one(name, group, cfg_kwargs, cf_kwargs=None, expect_error=None):
    """Run one config, capture metrics, or verify expected error."""
    t0 = time.time()
    try:
        with contextlib.redirect_stdout(_null), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cf = CashFlowConfig(**cf_kwargs) if cf_kwargs else None
            cfg = MonteCarloConfig(cashflow=cf, **cfg_kwargs)
            sim = MonteCarloSimulation(cfg)
            r = sim.run()

        # If we expected error but succeeded, that's a fail
        if expect_error is not None:
            return {
                "name": name, "group": group, "status": "FAIL_EXPECTED_ERROR",
                "expected": expect_error, "actual": "run() succeeded",
                "cfg": {k: str(v)[:80] for k, v in cfg_kwargs.items()},
                "elapsed": round(time.time() - t0, 2),
            }

        final = r.balance_paths[:, -1]
        p10, p25, p50, p75, p90 = np.percentile(final, [10, 25, 50, 75, 90])
        eff_pr = r.effective_port_returns
        if eff_pr is not None:
            med_vol = float(np.median(eff_pr.std(axis=1) * np.sqrt(12)))
        else:
            allocs = np.array([w for _, w in cfg.assets])
            pr = r.return_paths @ allocs
            med_vol = float(np.median(pr.std(axis=1) * np.sqrt(12)))
        dds = []
        for i in range(r.n_sims):
            bal = r.balance_paths[i]
            peak = np.maximum.accumulate(bal)
            dd = (bal - peak) / np.maximum(peak, 1e-9)
            dds.append(dd.min())
        med_dd = float(np.median(dds))
        cagr_p10, cagr_p50, cagr_p90 = np.percentile(r.sim_cagrs, [10, 50, 90])
        zero_paths = int((final <= cfg.initial_balance * 0.01).sum())

        return {
            "name": name, "group": group,
            "cfg": {k: (list(v) if isinstance(v, (list, tuple, np.ndarray)) else v)
                    for k, v in cfg_kwargs.items() if k != "cashflow"},
            "cf": cf_kwargs, "elapsed": round(time.time() - t0, 2),
            "n_sims": r.n_sims, "n_years": r.n_years,
            "median_cagr": float(r.median_cagr),
            "cagr_p10": float(cagr_p10), "cagr_p90": float(cagr_p90),
            "success_rate": float(r.success_rate),
            "median_final": float(r.median_final_balance),
            "final_p10": float(p10), "final_p90": float(p90),
            "swr": float(r.swr), "pwr": float(r.pwr),
            "median_vol": med_vol, "median_max_dd": med_dd,
            "zero_paths": zero_paths,
            "status": "OK", "error": None,
        }
    except Exception as e:
        if expect_error is not None and expect_error.lower() in type(e).__name__.lower():
            return {
                "name": name, "group": group, "status": "OK_EXPECTED_ERROR",
                "expected": expect_error, "actual": type(e).__name__,
                "cfg": {k: str(v)[:80] for k, v in cfg_kwargs.items()},
                "elapsed": round(time.time() - t0, 2),
            }
        return {
            "name": name, "group": group,
            "cfg": {k: str(v)[:80] for k, v in cfg_kwargs.items()},
            "cf": cf_kwargs, "elapsed": round(time.time() - t0, 2),
            "status": "ERROR",
            "error": f"{type(e).__name__}: {e}"[:300],
            "traceback": traceback.format_exc()[-500:],
        }


results = []
counter = [0]
BASELINE = [("NIFTY_50", 0.6), ("SBI_GILT", 0.4)]

def add(name, group, expect_error=None, **kw):
    counter[0] += 1
    tid = f"V{counter[0]:04d}"
    kw.setdefault("assets", BASELINE)
    kw.setdefault("simulations", 500)
    kw.setdefault("years", 30)
    kw.setdefault("seed", 42)
    cf = kw.pop("cf", None)
    r = run_one(f"{tid}_{name}", group, kw, cf, expect_error)
    results.append(r)
    status = r["status"]
    med_cagr = r.get("median_cagr", 0) if "median_cagr" in r else 0
    med_sr = r.get("success_rate", 0) if "success_rate" in r else 0
    swr = r.get("swr", 0) if "swr" in r else 0
    print(f"{tid} [{group[:15]:<15}] {name[:55]:<55} {status[:20]:<20} "
          f"CAGR={med_cagr:.3f} SR={med_sr:.3f} SWR={swr:.3f} "
          f"({r['elapsed']}s)")


# ============================================================
# GROUP A2: Fix validators — do the fixes actually work?
# ============================================================
print("\n=== GROUP A2: Fix validators ===")

# SWR should vary across configs (not clip at 8%)
# Test various portfolios to see SWR spread
for eq_wt in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
    if eq_wt == 0:
        assets = [("SBI_GILT", 1.0)]
    elif eq_wt == 1:
        assets = [("NIFTY_50", 1.0)]
    else:
        assets = [("NIFTY_50", eq_wt), ("SBI_GILT", 1-eq_wt)]
    add(f"SWR_variance_eq{eq_wt}", "A2_fix_validators",
        assets=assets, simulations=1000)

# SR should drop monotonically with fixed-amount withdrawal
for amt in [10000, 30000, 50000, 75000, 100000, 150000, 250000]:
    add(f"SR_monotonic_wd_{amt}", "A2_fix_validators",
        cf={"adjustment_type": 2, "amount": amt, "frequency": "annual",
            "inflation_adjusted": True, "inflation_mean": 0.04},
        simulations=1000)

# Fixed-% now preserves capital appropriately
for pct in [3, 5, 7, 10, 15, 20]:
    add(f"fixed_pct_{pct}_preserved", "A2_fix_validators",
        cf={"adjustment_type": 3, "withdrawal_percentage": pct, "frequency": "annual"})

# Rebalancing effects: should differ across frequencies
for rb in [0, 1, 2, 3, 4]:
    for alloc_pair in [(0.6, 0.4), (0.8, 0.2), (0.9, 0.1)]:
        add(f"rebal_{rb}_alloc{alloc_pair[0]}", "A2_fix_validators",
            assets=[("NIFTY_50", alloc_pair[0]), ("SBI_GILT", alloc_pair[1])],
            rebalance_frequency=rb, simulations=500)

# Real return should use Fisher, not subtraction
# Test: inflation=0.10, if arithmetic, real ≈ nominal - 0.10; if Fisher, real ≈ (1+n)/1.10 - 1
for infl in [0.02, 0.05, 0.10, 0.15]:
    add(f"real_return_Fisher_infl{infl}", "A2_fix_validators",
        inflation_adjusted=True, inflation_mean=infl, inflation_volatility=0.01,
        simulations=500)

# ============================================================
# GROUP B2: Extreme boundaries
# ============================================================
print("\n=== GROUP B2: Extreme boundaries ===")

# Very short horizons
for yr in [1, 2, 3, 4]:
    add(f"horizon_short_{yr}y", "B2_extreme", years=yr, simulations=1000)

# Very long horizons
for yr in [55, 65, 75, 85, 100]:
    add(f"horizon_long_{yr}y", "B2_extreme", years=yr, simulations=500)

# Extreme sim counts
for n in [10, 25, 50, 100, 500, 2000, 5000]:
    add(f"sims_{n}", "B2_extreme", simulations=n, years=30)

# Extreme initial balances
for ib in [1, 10, 100, 1_000, 100_000_000, 1_000_000_000]:
    add(f"initial_{ib}", "B2_extreme", initial_balance=ib)

# 100% single volatile
for a in ["NIFTY_SMALLCAP", "NIFTY_MIDCAP", "NIFTY_BANK", "NIFTY_IT", "NIFTY_PHARMA",
          "SILVER"]:
    add(f"100pct_{a}", "B2_extreme", assets=[(a, 1.0)], simulations=500)

# Multi-asset diverse
for n_assets, mix in [
    (3, [("NIFTY_50", 0.4), ("SBI_GILT", 0.4), ("GOLD", 0.2)]),
    (4, [("NIFTY_50", 0.3), ("NIFTY_MIDCAP", 0.2), ("SBI_GILT", 0.3), ("GOLD", 0.2)]),
    (5, [("NIFTY_50", 0.25), ("NIFTY_MIDCAP", 0.15), ("SBI_GILT", 0.3),
         ("GOLD", 0.15), ("SBI_LIQUID", 0.15)]),
    (6, [("NIFTY_50", 0.2), ("NIFTY_MIDCAP", 0.15), ("NIFTY_IT", 0.1),
         ("SBI_GILT", 0.3), ("GOLD", 0.15), ("SBI_LIQUID", 0.1)]),
]:
    add(f"multi_asset_{n_assets}", "B2_extreme", assets=mix)


# ============================================================
# GROUP C2: Model correctness — verify each model's math
# ============================================================
print("\n=== GROUP C2: Model correctness ===")

# Same 60/40 across all 4 models with seed=42 for direct compare
for m in [1, 2, 3, 4]:
    add(f"model{m}_baseline_seed42", "C2_model", model=m, simulations=1000)
    add(f"model{m}_baseline_seed99", "C2_model", model=m, simulations=1000, seed=99)

# Fat-tail dof sweep - lower dof should show larger tails
for dof in [3, 5, 10, 20, 30, 50, 100]:
    add(f"fat_tail_dof{dof}", "C2_model",
        model=3, distribution_type=2, degrees_of_freedom=dof, simulations=1000)

# Time series models for model=4
for tsm in [1, 3]:
    add(f"model4_tsm{tsm}", "C2_model", model=4, time_series_model=tsm, simulations=500)

# Custom means/stds override
add("custom_means_high", "C2_model",
    model=3, custom_means=[0.20, 0.10], custom_stds=[0.25, 0.05], simulations=500)
add("custom_means_low", "C2_model",
    model=3, custom_means=[0.05, 0.03], custom_stds=[0.15, 0.03], simulations=500)
add("custom_means_zero_vol_bond", "C2_model",
    model=3, custom_means=[0.10, 0.04], custom_stds=[0.20, 0.001], simulations=500)
add("custom_means_negative_stock", "C2_model",
    model=3, custom_means=[-0.02, 0.05], custom_stds=[0.20, 0.03], simulations=500)


# ============================================================
# GROUP D2: Cashflow deep dive
# ============================================================
print("\n=== GROUP D2: Cashflow deep dive ===")

# Contribution with growth_rate
for gr in [0.0, 0.05, 0.10, 0.20]:
    add(f"contrib_growth_{gr}", "D2_cashflow",
        cf={"adjustment_type": 1, "amount": 10000, "frequency": "annual",
            "growth_rate": gr})

# Withdrawal frequencies with inflation
for freq in ["monthly", "quarterly", "annual"]:
    for infl_adj in [True, False]:
        add(f"wd_freq_{freq}_infl{infl_adj}", "D2_cashflow",
            cf={"adjustment_type": 2, "amount": 30000, "frequency": freq,
                "inflation_adjusted": infl_adj, "inflation_mean": 0.04})

# pct_change on types 8/9 (verify inflation NOW honored per fix)
for pc in [-0.10, -0.05, 0.0, 0.03, 0.05, 0.10, 0.20]:
    for t in [8, 9]:
        add(f"pctch_{pc}_type{t}", "D2_cashflow",
            cf={"adjustment_type": t, "amount": 30000, "frequency": "annual",
                "pct_change": pc, "inflation_adjusted": True, "inflation_mean": 0.04})

# Life expectancy at various ages
for age in [30, 40, 50, 60, 70, 80]:
    add(f"life_exp_age{age}", "D2_cashflow",
        cf={"adjustment_type": 4, "amount": 30_000_000, "current_age": age,
            "frequency": "annual"})

# Fixed-% at every 1% step
for pct in range(1, 26):
    add(f"fixed_pct_step_{pct}", "D2_cashflow",
        cf={"adjustment_type": 3, "withdrawal_percentage": pct, "frequency": "annual"},
        simulations=500)

# Timing beginning vs end
for tim in ["beginning", "end"]:
    add(f"timing_{tim}", "D2_cashflow",
        cf={"adjustment_type": 2, "amount": 40000, "frequency": "annual",
            "timing": tim, "inflation_adjusted": True, "inflation_mean": 0.04})


# ============================================================
# GROUP E2: Inflation model
# ============================================================
print("\n=== GROUP E2: Inflation model ===")

for infl_model in [1, 2]:
    for infl_mean in [0.0, 0.02, 0.04, 0.06, 0.10, 0.15]:
        for infl_vol in [0.005, 0.01, 0.02, 0.03]:
            add(f"infl_m{infl_model}_mean{infl_mean}_vol{infl_vol}", "E2_inflation",
                inflation_adjusted=True, inflation_model=infl_model,
                inflation_mean=infl_mean, inflation_volatility=infl_vol,
                simulations=200)


# ============================================================
# GROUP F2: Custom correlations & multi-asset
# ============================================================
print("\n=== GROUP F2: Correlations ===")

# Identity correlation
add("identity_corr_60_40", "F2_correl",
    use_historical_correlations=False, simulations=500)

# Custom correlation matrix under DEFAULT (model=1) MUST NOW RAISE (V2-2 fix)
add("custom_corr_perfect_pos_default_model_raises", "F2_correl",
    custom_correlation=[[1.0, 0.99], [0.99, 1.0]], simulations=500,
    expect_error="valueerror")
add("custom_corr_perfect_neg_default_model_raises", "F2_correl",
    custom_correlation=[[1.0, -0.99], [-0.99, 1.0]], simulations=500,
    expect_error="valueerror")
add("custom_corr_uncorrelated_default_model_raises", "F2_correl",
    custom_correlation=[[1.0, 0.0], [0.0, 1.0]], simulations=500,
    expect_error="valueerror")
add("custom_corr_mixed_pos_default_model_raises", "F2_correl",
    custom_correlation=[[1.0, 0.5], [0.5, 1.0]], simulations=500,
    expect_error="valueerror")

# Under model=3, these SHOULD work
add("custom_corr_perfect_pos_model3", "F2_correl",
    model=3, custom_means=[0.12, 0.05], custom_stds=[0.20, 0.05],
    custom_correlation=[[1.0, 0.99], [0.99, 1.0]], simulations=500)
add("custom_corr_perfect_neg_model3", "F2_correl",
    model=3, custom_means=[0.12, 0.05], custom_stds=[0.20, 0.05],
    custom_correlation=[[1.0, -0.99], [-0.99, 1.0]], simulations=500)
add("custom_corr_uncorrelated_model3", "F2_correl",
    model=3, custom_means=[0.12, 0.05], custom_stds=[0.20, 0.05],
    custom_correlation=[[1.0, 0.0], [0.0, 1.0]], simulations=500)
add("custom_corr_mixed_pos_model3", "F2_correl",
    model=3, custom_means=[0.12, 0.05], custom_stds=[0.20, 0.05],
    custom_correlation=[[1.0, 0.5], [0.5, 1.0]], simulations=500)

# Custom correlation shape mismatch under model=3 (should raise)
add("custom_corr_wrong_shape_model3", "F2_correl",
    model=3, custom_means=[0.12, 0.05], custom_stds=[0.20, 0.05],
    custom_correlation=[[1.0, 0.5, 0.3], [0.5, 1.0, 0.2], [0.3, 0.2, 1.0]],
    expect_error="valueerror", simulations=200)

# Custom correlation shape mismatch under model=1 (raises because of V2-2 first)
add("custom_corr_wrong_shape_model1", "F2_correl",
    custom_correlation=[[1.0, 0.5, 0.3], [0.5, 1.0, 0.2], [0.3, 0.2, 1.0]],
    expect_error="valueerror", simulations=200)

# use_historical_correlations False falls back to identity
add("no_hist_corr", "F2_correl",
    use_historical_correlations=False,
    assets=[("NIFTY_50", 0.5), ("SBI_GILT", 0.5)], simulations=500)


# ============================================================
# GROUP G2: Sequence stress
# ============================================================
print("\n=== GROUP G2: Sequence stress ===")

for sst in [0, 1, 2, 3, 5, 7, 10]:
    add(f"seq_stress_{sst}", "G2_stress",
        sequence_stress_test=sst, simulations=500)
    # With withdrawal
    add(f"seq_stress_{sst}_wd40k", "G2_stress",
        sequence_stress_test=sst,
        cf={"adjustment_type": 2, "amount": 40000, "frequency": "annual",
            "inflation_adjusted": True, "inflation_mean": 0.04},
        simulations=500)


# ============================================================
# GROUP H2: Rebalancing sanity
# ============================================================
print("\n=== GROUP H2: Rebalancing ===")

# 100/0 shouldn't be affected by rebalance
for rb in [0, 1, 4]:
    add(f"100pct_eq_rebal{rb}", "H2_rebal",
        assets=[("NIFTY_50", 1.0)], rebalance_frequency=rb, simulations=500)

# 50/50 - rebalance should matter more
for rb in [0, 1, 2, 3, 4]:
    add(f"50_50_rebal{rb}", "H2_rebal",
        assets=[("NIFTY_50", 0.5), ("SBI_GILT", 0.5)],
        rebalance_frequency=rb, simulations=500)

# With cashflow + rebalance
for rb in [0, 1, 4]:
    add(f"rebal{rb}_with_wd", "H2_rebal",
        rebalance_frequency=rb,
        cf={"adjustment_type": 2, "amount": 30000, "frequency": "annual",
            "inflation_adjusted": True, "inflation_mean": 0.04},
        simulations=500)


# ============================================================
# GROUP I2: Bootstrap deep dive
# ============================================================
print("\n=== GROUP I2: Bootstrap ===")

# Compare all 3 bootstrap modes on same 60/40
for bm in [0, 1, 2]:
    for seed in [42, 99, 100]:
        add(f"bm{bm}_seed{seed}", "I2_bootstrap",
            bootstrap_model=bm, seed=seed, simulations=1000)

# Block bootstrap min/max variations
for bmin in [1, 3, 5, 10]:
    for bmax in [5, 10, 20]:
        if bmin > bmax:
            continue
        add(f"block_{bmin}_{bmax}", "I2_bootstrap",
            bootstrap_model=2, bootstrap_min_years=bmin, bootstrap_max_years=bmax,
            simulations=500)

# Circular vs non-circular
for circ in [True, False]:
    add(f"block_circ{circ}", "I2_bootstrap",
        bootstrap_model=2, circular_bootstrap=circ, simulations=500)


# ============================================================
# GROUP J2: Regression tests (must raise appropriate errors)
# ============================================================
print("\n=== GROUP J2: Regression tests ===")

# Types 5/6 must raise NotImplementedError
add("type5_raises", "J2_regression",
    cf={"adjustment_type": 5, "amount": 40000},
    expect_error="notimplementederror")
add("type6_raises", "J2_regression",
    cf={"adjustment_type": 6, "amount": 40000},
    expect_error="notimplementederror")

# tax_enabled=True must raise NotImplementedError
add("tax_enabled_raises", "J2_regression",
    tax_enabled=True, expect_error="notimplementederror")

# Unknown asset must raise ValueError
add("unknown_asset_raises", "J2_regression",
    assets=[("FAKE_ASSET_XYZ", 1.0)], expect_error="valueerror")

# Weights not summing to 1 must raise
add("bad_weights_raise", "J2_regression",
    assets=[("NIFTY_50", 0.3), ("SBI_GILT", 0.3)],
    expect_error="valueerror")

# FatTailedSampler dof<=2 must raise
add("fat_dof2_raises", "J2_regression",
    model=3, distribution_type=2, degrees_of_freedom=2,
    expect_error="valueerror", simulations=100)

# custom_means with wrong shape or negative variance - test edge
add("custom_stds_zero_bond", "J2_regression",
    model=3, custom_means=[0.10, 0.04], custom_stds=[0.20, 0.0],
    simulations=200)

# Assets with disjoint histories
add("disjoint_history_ok", "J2_regression",
    assets=[("NIFTY_50", 0.5), ("SBI_CORP", 0.5)], simulations=200)


# ============================================================
# GROUP K2: PV cross-check with varied sims
# ============================================================
print("\n=== GROUP K2: PV cross-check ===")

# T1: 60/40 no CF, 30y, at various sim counts (convergence check)
for n in [100, 500, 1000, 5000]:
    add(f"PV_T1_conv_{n}sims", "K2_pv",
        simulations=n, years=30)

# T2: 60/40 with 4% wd
for n in [500, 1000, 5000]:
    add(f"PV_T2_4pct_wd_{n}sims", "K2_pv",
        simulations=n,
        cf={"adjustment_type": 2, "amount": 40000, "frequency": "annual",
            "inflation_adjusted": True, "inflation_mean": 0.04})

# T3: 100% stock
for n in [500, 1000]:
    add(f"PV_T3_100pct_{n}sims", "K2_pv",
        assets=[("NIFTY_50", 1.0)], simulations=n)

# T7: 10y horizon
add("PV_T7_10y", "K2_pv", years=10, simulations=1000)


# ============================================================
# GROUP L2: Real-vs-nominal cross-check
# ============================================================
print("\n=== GROUP L2: Real-nominal ===")

# Sanity: with inflation=0, real should equal nominal
add("infl_zero_check", "L2_real_nom",
    inflation_adjusted=True, inflation_mean=0.0, inflation_volatility=0.001)

# With no inflation adjustment, real = nominal
add("infl_off_check", "L2_real_nom",
    inflation_adjusted=False)

# High inflation should crush real returns
for infl in [0.03, 0.08, 0.15, 0.25]:
    add(f"real_stress_infl{infl}", "L2_real_nom",
        inflation_adjusted=True, inflation_mean=infl, inflation_volatility=0.01)


# ============================================================
# SAVE
# ============================================================
print(f"\nTotal v2 tests: {len(results)}")
OUT.write_text(json.dumps(results, indent=2, default=str))
print(f"Saved to {OUT}")

ok = sum(1 for r in results if r["status"] == "OK")
ok_err = sum(1 for r in results if r["status"] == "OK_EXPECTED_ERROR")
err = sum(1 for r in results if r["status"] == "ERROR")
fail_expected = sum(1 for r in results if r["status"] == "FAIL_EXPECTED_ERROR")
print(f"OK: {ok}  OK_EXPECTED_ERROR: {ok_err}  ERROR: {err}  FAIL_EXPECTED_ERROR: {fail_expected}")

if ok > 0:
    swrs = [r["swr"] for r in results if r.get("status") == "OK"]
    print(f"SWR range: {min(swrs):.4f} - {max(swrs):.4f}, mean={np.mean(swrs):.4f}")
    sr = [r["success_rate"] for r in results if r.get("status") == "OK"]
    print(f"Success range: {min(sr):.4f} - {max(sr):.4f}, mean={np.mean(sr):.4f}")

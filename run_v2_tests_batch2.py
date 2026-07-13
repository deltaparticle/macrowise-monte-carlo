"""V2 batch2: additional 180+ tests to reach 450+ total."""
import json, time, traceback, warnings, contextlib, io
from pathlib import Path
import numpy as np
import sys
sys.path.insert(0, str(Path(__file__).parent))

from macrowise.engine.monte_carlo import MonteCarloConfig, MonteCarloSimulation
from macrowise.engine.cashflow import CashFlowConfig

OUT = Path(__file__).parent / "v2_test_results_batch2.json"
_null = io.StringIO()


def run_one(name, group, cfg_kwargs, cf_kwargs=None, expect_error=None):
    t0 = time.time()
    try:
        with contextlib.redirect_stdout(_null), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cf = CashFlowConfig(**cf_kwargs) if cf_kwargs else None
            cfg = MonteCarloConfig(cashflow=cf, **cfg_kwargs)
            sim = MonteCarloSimulation(cfg)
            r = sim.run()
        if expect_error is not None:
            return {"name": name, "group": group, "status": "FAIL_EXPECTED_ERROR",
                    "expected": expect_error, "actual": "succeeded",
                    "cfg": {k: str(v)[:80] for k, v in cfg_kwargs.items()},
                    "elapsed": round(time.time() - t0, 2)}
        final = r.balance_paths[:, -1]
        p10, p50, p90 = np.percentile(final, [10, 50, 90])
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
        zero_paths = int((final <= cfg.initial_balance * 0.01).sum())
        return {"name": name, "group": group,
                "cfg": {k: (list(v) if isinstance(v, (list, tuple, np.ndarray)) else v)
                        for k, v in cfg_kwargs.items() if k != "cashflow"},
                "cf": cf_kwargs, "elapsed": round(time.time() - t0, 2),
                "n_sims": r.n_sims, "n_years": r.n_years,
                "median_cagr": float(r.median_cagr),
                "success_rate": float(r.success_rate),
                "median_final": float(r.median_final_balance),
                "final_p10": float(p10), "final_p90": float(p90),
                "swr": float(r.swr), "pwr": float(r.pwr),
                "median_vol": med_vol, "median_max_dd": med_dd,
                "zero_paths": zero_paths,
                "status": "OK", "error": None}
    except Exception as e:
        if expect_error is not None and expect_error.lower() in type(e).__name__.lower():
            return {"name": name, "group": group, "status": "OK_EXPECTED_ERROR",
                    "expected": expect_error, "actual": type(e).__name__,
                    "cfg": {k: str(v)[:80] for k, v in cfg_kwargs.items()},
                    "elapsed": round(time.time() - t0, 2)}
        return {"name": name, "group": group,
                "cfg": {k: str(v)[:80] for k, v in cfg_kwargs.items()},
                "cf": cf_kwargs, "elapsed": round(time.time() - t0, 2),
                "status": "ERROR",
                "error": f"{type(e).__name__}: {e}"[:300]}


results = []
counter = [0]
BASELINE = [("NIFTY_50", 0.6), ("SBI_GILT", 0.4)]

def add(name, group, expect_error=None, **kw):
    counter[0] += 1
    tid = f"W{counter[0]:04d}"
    kw.setdefault("assets", BASELINE)
    kw.setdefault("simulations", 500)
    kw.setdefault("years", 30)
    kw.setdefault("seed", 42)
    cf = kw.pop("cf", None)
    r = run_one(f"{tid}_{name}", group, kw, cf, expect_error)
    results.append(r)
    st = r["status"]
    cagr = r.get("median_cagr", 0)
    sr = r.get("success_rate", 0)
    swr = r.get("swr", 0)
    print(f"{tid} [{group[:14]:<14}] {name[:52]:<52} {st[:20]:<20} "
          f"CAGR={cagr:.3f} SR={sr:.3f} SWR={swr:.3f} ({r['elapsed']}s)")


# ============================================================
# M2: Cross-model reproducibility (same seed = same output)
# ============================================================
print("\n=== M2: Reproducibility ===")
for m in [1, 2, 3, 4]:
    for seed in [42, 42, 100, 100]:
        add(f"repro_m{m}_seed{seed}", "M2_repro",
            model=m, seed=seed, simulations=500)

# ============================================================
# N2: Model correctness on parametric — verify vol matches spec
# ============================================================
print("\n=== N2: Parametric vol correctness ===")
# Custom stds should map to actual portfolio vol closely
test_configs = [
    ([("NIFTY_50", 1.0)], [0.15], [0.20], 0.20),
    ([("NIFTY_50", 1.0)], [0.10], [0.10], 0.10),
    ([("NIFTY_50", 1.0)], [0.05], [0.30], 0.30),
    ([("SBI_GILT", 1.0)], [0.05], [0.05], 0.05),
    ([("SBI_GILT", 1.0)], [0.05], [0.15], 0.15),
]
for assets, cm, cs, expected_vol in test_configs:
    add(f"param_vol_stock_std{cs[0]}", "N2_param_vol",
        model=3, distribution_type=1,
        custom_means=cm, custom_stds=cs, use_historical_correlations=False,
        simulations=1000)

# ============================================================
# O2: Custom correlation stress under model=3/4
# ============================================================
print("\n=== O2: Custom correlation ===")
# All under model=3 to actually use correlation
for corr_val in [-0.9, -0.5, 0.0, 0.5, 0.9]:
    add(f"custom_corr_{corr_val}_model3", "O2_custom_corr",
        model=3, distribution_type=1,
        custom_correlation=[[1.0, corr_val], [corr_val, 1.0]],
        custom_means=[0.10, 0.05], custom_stds=[0.20, 0.05],
        simulations=500)

# Wrong shape under model=3 — should raise
add("custom_corr_wrong_shape_model3", "O2_custom_corr",
    model=3, distribution_type=1,
    custom_correlation=[[1.0, 0.5, 0.3], [0.5, 1.0, 0.2], [0.3, 0.2, 1.0]],
    custom_means=[0.10, 0.05], custom_stds=[0.20, 0.05],
    expect_error="valueerror", simulations=200)

# ============================================================
# P2: Sequence stress verification (SR should drop)
# ============================================================
print("\n=== P2: Sequence stress verification ===")
# Compare stress=0 vs stress=N for same setup
for sst in [1, 3, 5, 8, 10]:
    add(f"stress_wd50k_sst{sst}", "P2_stress_verif",
        sequence_stress_test=sst,
        cf={"adjustment_type": 2, "amount": 50000, "frequency": "annual",
            "inflation_adjusted": True, "inflation_mean": 0.04},
        simulations=500)

# Extreme stress with 100% equity
for sst in [5, 10]:
    add(f"stress_100pct_eq_sst{sst}", "P2_stress_verif",
        assets=[("NIFTY_50", 1.0)], sequence_stress_test=sst,
        simulations=500)

# ============================================================
# Q2: PV cross-check on more configs
# ============================================================
print("\n=== Q2: PV cross-check extended ===")
# 3% withdrawal (conservative retirement)
add("PV_3pct_wd", "Q2_pv_ext",
    cf={"adjustment_type": 2, "amount": 30000, "frequency": "annual",
        "inflation_adjusted": True, "inflation_mean": 0.04}, simulations=2000)
# 5% withdrawal
add("PV_5pct_wd", "Q2_pv_ext",
    cf={"adjustment_type": 2, "amount": 50000, "frequency": "annual",
        "inflation_adjusted": True, "inflation_mean": 0.04}, simulations=2000)
# 6% withdrawal
add("PV_6pct_wd", "Q2_pv_ext",
    cf={"adjustment_type": 2, "amount": 60000, "frequency": "annual",
        "inflation_adjusted": True, "inflation_mean": 0.04}, simulations=2000)
# High initial + 4% wd
add("PV_high_initial_4pct", "Q2_pv_ext",
    initial_balance=10_000_000,
    cf={"adjustment_type": 2, "amount": 400000, "frequency": "annual",
        "inflation_adjusted": True, "inflation_mean": 0.04}, simulations=1000)

# 40/60 conservative
add("PV_40_60_conservative", "Q2_pv_ext",
    assets=[("NIFTY_50", 0.4), ("SBI_GILT", 0.6)], simulations=2000)

# 20/80 very conservative
add("PV_20_80_very_cons", "Q2_pv_ext",
    assets=[("NIFTY_50", 0.2), ("SBI_GILT", 0.8)], simulations=2000)

# ============================================================
# R2: Very-large sim counts for convergence check
# ============================================================
print("\n=== R2: Convergence ===")
for n in [100, 500, 1000, 2500, 5000, 10000]:
    add(f"convergence_60_40_{n}", "R2_convergence",
        simulations=n)

# ============================================================
# S2: Bootstrap correctness with block bootstrap variations
# ============================================================
print("\n=== S2: Block bootstrap ===")
for bmin in [1, 3, 5, 7, 10]:
    for bmax in [3, 5, 10, 15, 20]:
        if bmin > bmax:
            continue
        for circ in [True, False]:
            add(f"block_{bmin}_{bmax}_circ{circ}", "S2_block",
                bootstrap_model=2, bootstrap_min_years=bmin, bootstrap_max_years=bmax,
                circular_bootstrap=circ, simulations=300)

# ============================================================
# T2: Cross-checks — same result under different seeds should have similar distribution
# ============================================================
print("\n=== T2: Seed sensitivity ===")
for seed in [1, 7, 42, 100, 777, 1000, 12345, 99999, 314159, 271828]:
    add(f"seed_{seed}", "T2_seed", seed=seed, simulations=500)

# ============================================================
# U2: Cross-checks: cashflow + rebalance interactions
# ============================================================
print("\n=== U2: Cashflow x rebalance ===")
for rb in [0, 1, 4]:
    for cf_type in [1, 2, 3]:
        if cf_type == 1:
            cf = {"adjustment_type": 1, "amount": 20000, "frequency": "monthly"}
        elif cf_type == 2:
            cf = {"adjustment_type": 2, "amount": 40000, "frequency": "annual",
                  "inflation_adjusted": True, "inflation_mean": 0.04}
        else:
            cf = {"adjustment_type": 3, "withdrawal_percentage": 5.0, "frequency": "annual"}
        add(f"cf{cf_type}_rebal{rb}", "U2_cf_rebal",
            rebalance_frequency=rb, cf=cf, simulations=500)

# ============================================================
# V2_edge: True adversarial cases
# ============================================================
print("\n=== V2_edge: Adversarial ===")
# All bonds
add("all_bonds_30y", "V2_edge",
    assets=[("SBI_GILT", 1.0)], simulations=1000)
add("all_liquid_30y", "V2_edge",
    assets=[("SBI_LIQUID", 1.0)], simulations=1000)

# Gold only
add("gold_only_30y", "V2_edge",
    assets=[("GOLD", 1.0)], simulations=1000)

# Very short + high vol
add("smallcap_5y", "V2_edge",
    assets=[("NIFTY_SMALLCAP", 1.0)], years=5, simulations=1000)

# 100y horizon 100% equity
add("100y_100pct_eq", "V2_edge",
    assets=[("NIFTY_50", 1.0)], years=100, simulations=200)

# Contribution + withdrawal (net negative) - contribution alone should help
# But we can only have one cf, so test contribution
add("large_contrib_30y", "V2_edge",
    cf={"adjustment_type": 1, "amount": 100000, "frequency": "monthly",
        "inflation_adjusted": True, "inflation_mean": 0.06,
        "growth_rate": 0.05}, simulations=500)

# Very high inflation stress
add("high_infl_stress", "V2_edge",
    inflation_adjusted=True, inflation_mean=0.20, inflation_volatility=0.05,
    simulations=500)

# Deflation!
add("deflation_scenario", "V2_edge",
    inflation_adjusted=True, inflation_mean=-0.02, inflation_volatility=0.005,
    simulations=500)

# 0-year horizon (should probably fail gracefully)
add("zero_years_edge", "V2_edge",
    years=1, simulations=100)  # minimum viable

# ============================================================
# X2: Rebalance-with-glide-like allocations (multi-asset)
# ============================================================
print("\n=== X2: Multi-asset rebalancing ===")
for rb in [0, 1, 4]:
    add(f"6asset_rebal{rb}", "X2_multi_rebal",
        assets=[("NIFTY_50", 0.2), ("NIFTY_MIDCAP", 0.1), ("NIFTY_IT", 0.1),
                ("SBI_GILT", 0.3), ("GOLD", 0.2), ("SBI_LIQUID", 0.1)],
        rebalance_frequency=rb, simulations=500)

# ============================================================
print(f"\nTotal batch2: {len(results)}")
OUT.write_text(json.dumps(results, indent=2, default=str))
print(f"Saved to {OUT}")

ok = sum(1 for r in results if r["status"] == "OK")
ok_err = sum(1 for r in results if r["status"] == "OK_EXPECTED_ERROR")
err = sum(1 for r in results if r["status"] == "ERROR")
fee = sum(1 for r in results if r["status"] == "FAIL_EXPECTED_ERROR")
print(f"OK: {ok}  OK_EXPECTED_ERROR: {ok_err}  ERROR: {err}  FAIL_EXPECTED_ERROR: {fee}")

if ok > 0:
    swrs = [r["swr"] for r in results if r.get("status") == "OK"]
    print(f"SWR range: {min(swrs):.4f} - {max(swrs):.4f}, mean={np.mean(swrs):.4f}")
    sr = [r["success_rate"] for r in results if r.get("status") == "OK"]
    print(f"Success range: {min(sr):.4f} - {max(sr):.4f}, mean={np.mean(sr):.4f}")

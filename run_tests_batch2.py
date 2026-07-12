"""Batch 2: focused stress/withdrawal/seed/deep tests."""
import json, time, traceback
from pathlib import Path
import numpy as np
import sys
sys.path.insert(0, str(Path(__file__).parent))

from macrowise.engine.monte_carlo import MonteCarloConfig, MonteCarloSimulation
from macrowise.engine.cashflow import CashFlowConfig

OUT = Path(__file__).parent / "exhaustive_test_results_batch2.json"

def run_one(name, group, cfg_kwargs, cf_kwargs=None):
    t0 = time.time()
    try:
        cf = CashFlowConfig(**cf_kwargs) if cf_kwargs else None
        cfg = MonteCarloConfig(cashflow=cf, **cfg_kwargs)
        sim = MonteCarloSimulation(cfg)
        r = sim.run()
        final = r.balance_paths[:, -1]
        p10, p25, p50, p75, p90 = np.percentile(final, [10, 25, 50, 75, 90])
        allocs = np.array([w for _, w in cfg.assets])
        port_ret = r.return_paths @ allocs
        med_vol = float(np.median(port_ret.std(axis=1) * np.sqrt(12)))
        dds = []
        for i in range(r.n_sims):
            bal = r.balance_paths[i]
            peak = np.maximum.accumulate(bal)
            dd = (bal - peak) / np.maximum(peak, 1e-9)
            dds.append(dd.min())
        med_dd = float(np.median(dds))
        cagr_p10, cagr_p50, cagr_p90 = np.percentile(r.sim_cagrs, [10, 50, 90])
        # Zero-balance count (depleted paths)
        zero_paths = int((final <= 1.0).sum())
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
        return {"name": name, "group": group, "cfg": cfg_kwargs, "cf": cf_kwargs,
                "elapsed": round(time.time() - t0, 2), "status": "ERROR",
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[-500:]}

BASELINE = [("NIFTY_50", 0.6), ("SBI_GILT", 0.4)]
results = []
counter = [0]

def add(name, group, **kw):
    counter[0] += 1
    tid = f"B{counter[0]:04d}"
    kw.setdefault("assets", BASELINE)
    kw.setdefault("simulations", 500)
    kw.setdefault("years", 30)
    kw.setdefault("seed", 42)
    cf = kw.pop("cf", None)
    r = run_one(f"{tid}_{name}", group, kw, cf)
    results.append(r)
    print(f"{tid} [{group}] {name[:55]:<55} "
          f"{'OK' if r['status']=='OK' else 'ERR'}  "
          f"CAGR={r.get('median_cagr',0):.3f} SR={r.get('success_rate',0):.3f} "
          f"SWR={r.get('swr',0):.3f} MedFin={r.get('median_final',0)/1e6:.1f}M "
          f"Zero={r.get('zero_paths',0)} ({r['elapsed']}s)")

# ============================================================
# H: PV replication tests (match PV agent's config)
# ============================================================
print("\n=== H: PV replication ===")
# T1 equivalent
add("PV_T1_60_40_no_cf_30y", "H_PV",
    initial_balance=1_000_000, years=30, assets=BASELINE,
    model=1, bootstrap_model=1, inflation_adjusted=True, simulations=1000)
# T2 equivalent (4% withdrawal)
add("PV_T2_60_40_wd_40k_annual", "H_PV",
    initial_balance=1_000_000, years=30, assets=BASELINE,
    model=1, bootstrap_model=1, inflation_adjusted=True, simulations=1000,
    cf={"adjustment_type":2, "amount":40000, "frequency":"annual",
        "inflation_adjusted":True, "inflation_mean":0.04})
# T3 = 100% equity
add("PV_T3_100pct_stock", "H_PV",
    initial_balance=1_000_000, years=30, assets=[("NIFTY_50",1.0)],
    model=1, simulations=1000)
# T4 = 80/20 with 5% withdrawal
add("PV_T4_80_20_wd_50k", "H_PV",
    initial_balance=1_000_000, years=30,
    assets=[("NIFTY_50",0.8),("SBI_GILT",0.2)],
    model=1, simulations=1000,
    cf={"adjustment_type":2, "amount":50000, "frequency":"annual",
        "inflation_adjusted":True, "inflation_mean":0.04})
# T5 = 6% fixed % (this should have 100% SR since balance never depletes)
add("PV_T5_60_40_6pct_fixed", "H_PV",
    initial_balance=1_000_000, years=30, assets=BASELINE,
    model=1, simulations=1000,
    cf={"adjustment_type":3, "withdrawal_percentage":6.0, "frequency":"annual"})
# T6 = +$24k/yr contribution
add("PV_T6_60_40_contrib_24k", "H_PV",
    initial_balance=1_000_000, years=30, assets=BASELINE,
    model=1, simulations=1000,
    cf={"adjustment_type":1, "amount":24000, "frequency":"annual",
        "inflation_adjusted":True, "inflation_mean":0.04})
# T7 = 10y no cf
add("PV_T7_60_40_10y", "H_PV",
    initial_balance=1_000_000, years=10, assets=BASELINE,
    model=1, simulations=1000)
# T8 = Parameterized normal with modest params
add("PV_T8_parametric_conservative", "H_PV",
    initial_balance=1_000_000, years=30, assets=BASELINE,
    model=3, distribution_type=1, simulations=1000,
    custom_means=[0.10, 0.05], custom_stds=[0.15, 0.10])

# ============================================================
# I: Withdrawal stress - Fixed amount, various rates
# ============================================================
print("\n=== I: withdrawal stress ===")
# Fixed monthly withdrawal, varying amount
for amt in [5000, 10000, 20000, 40000, 60000, 80000, 100000, 150000, 200000, 300000]:
    add(f"wd_stress_{amt}_monthly", "I_wd_stress",
        cf={"adjustment_type":2, "amount":amt, "frequency":"monthly",
            "inflation_adjusted":True, "inflation_mean":0.04})

# Fixed % withdrawal at increasing rates (test if success drops)
for pct in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20, 25, 30]:
    add(f"pct_wd_stress_{pct}", "I_wd_stress",
        cf={"adjustment_type":3, "withdrawal_percentage":pct, "frequency":"annual"})

# Monthly fixed %
for pct in [0.5, 1.0, 2.0, 3.0]:
    add(f"pct_wd_monthly_{pct}", "I_wd_stress",
        cf={"adjustment_type":3, "withdrawal_percentage":pct, "frequency":"monthly"})

# High withdrawal on 100% equity (highest expected returns)
for amt in [40000, 100000, 200000, 500000]:
    add(f"100pct_eq_wd_{amt}", "I_wd_stress",
        assets=[("NIFTY_50", 1.0)],
        cf={"adjustment_type":2, "amount":amt, "frequency":"monthly"})

# High withdrawal on 100% gilt (conservative)
for amt in [30000, 60000, 100000]:
    add(f"100pct_gilt_wd_{amt}", "I_wd_stress",
        assets=[("SBI_GILT", 1.0)],
        cf={"adjustment_type":2, "amount":amt, "frequency":"monthly"})

# ============================================================
# J: Seed reproducibility
# ============================================================
print("\n=== J: seed reproducibility ===")
for seed in [1, 7, 42, 99, 100, 777, 12345, 99999]:
    add(f"seed_{seed}_repro", "J_seed",
        seed=seed, simulations=500)

# ============================================================
# K: Different equity/bond ratios × models
# ============================================================
print("\n=== K: model×alloc cross ===")
for eq in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
    for model in [1, 3, 4]:
        assets = [("NIFTY_50", eq)] if eq==1.0 else ([("SBI_GILT",1.0)] if eq==0.0 else [("NIFTY_50",eq),("SBI_GILT",1-eq)])
        add(f"eq{eq}_model{model}", "K_alloc_model",
            assets=assets, model=model, simulations=500)

# ============================================================
# L: Data quality tests - assets with short history
# ============================================================
print("\n=== L: short-history assets ===")
for a in ['SBI_CORP', 'SBI_LIQUID', 'SBI_GILT']:
    add(f"single_{a}_30y", "L_short_history", assets=[(a, 1.0)])
    add(f"single_{a}_5y", "L_short_history", assets=[(a, 1.0)], years=5)

# ============================================================
# M: Very long horizons
# ============================================================
print("\n=== M: extreme horizons ===")
for yrs in [1, 2, 3, 5, 10, 60, 70, 80, 100]:
    if yrs <= 100:
        add(f"horizon_{yrs}y", "M_horizon", years=yrs, simulations=500)

# ============================================================
# N: Combined stress
# ============================================================
print("\n=== N: combined stress ===")
# High withdrawal + high inflation
for infl in [0.05, 0.08, 0.15]:
    for pct in [4, 6, 8]:
        add(f"wd{pct}pct_infl{infl}", "N_combined",
            inflation_mean=infl, inflation_adjusted=True,
            cf={"adjustment_type":3, "withdrawal_percentage":pct, "frequency":"annual"})

# Sequence stress + high withdrawal
for sst in [3, 5, 10]:
    for wd_amt in [40000, 80000]:
        add(f"stress{sst}_wd{wd_amt}", "N_combined",
            sequence_stress_test=sst,
            cf={"adjustment_type":2, "amount":wd_amt, "frequency":"annual",
                "inflation_adjusted":True, "inflation_mean":0.04})

# Fat tail + stress
for dof in [3, 5, 10]:
    add(f"fat_tail_dof{dof}_stress", "N_combined",
        model=3, distribution_type=2, degrees_of_freedom=dof,
        sequence_stress_test=5,
        cf={"adjustment_type":3, "withdrawal_percentage":6.0, "frequency":"annual"})

# ============================================================
print(f"\nTotal batch2: {len(results)}")
OUT.write_text(json.dumps(results, indent=2, default=str))
print(f"Saved to {OUT}")

ok = sum(1 for r in results if r["status"] == "OK")
err = sum(1 for r in results if r["status"] == "ERROR")
print(f"OK: {ok}  ERROR: {err}")

swrs = [r["swr"] for r in results if r["status"] == "OK"]
print(f"SWR range: {min(swrs):.3f} - {max(swrs):.3f}, mean={np.mean(swrs):.3f}")
sr = [r["success_rate"] for r in results if r["status"] == "OK"]
print(f"Success range: {min(sr):.3f} - {max(sr):.3f}, mean={np.mean(sr):.3f}")

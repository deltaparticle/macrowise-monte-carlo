"""Exhaustive Monte Carlo test harness.

Runs ~640 configs across 7 dimensions and dumps JSON + summary.
"""
import json
import time
import traceback
from pathlib import Path
from itertools import product

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent))

from macrowise.engine.monte_carlo import MonteCarloConfig, MonteCarloSimulation
from macrowise.engine.cashflow import CashFlowConfig


OUT = Path(__file__).parent / "exhaustive_test_results.json"


def run_one(name, group, cfg_kwargs, cf_kwargs=None):
    """Run one config, return metrics dict."""
    t0 = time.time()
    try:
        cf = CashFlowConfig(**cf_kwargs) if cf_kwargs else None
        cfg = MonteCarloConfig(cashflow=cf, **cfg_kwargs)
        sim = MonteCarloSimulation(cfg)
        r = sim.run()

        # Extract percentiles of final balance
        final = r.balance_paths[:, -1]
        p10, p25, p50, p75, p90 = np.percentile(final, [10, 25, 50, 75, 90])

        # Volatility (median across sims)
        allocs = np.array([w for _, w in cfg.assets])
        port_ret = r.return_paths @ allocs
        vols = port_ret.std(axis=1) * np.sqrt(12)
        med_vol = float(np.median(vols))

        # Max drawdown (median)
        dds = []
        for i in range(r.n_sims):
            bal = r.balance_paths[i]
            peak = np.maximum.accumulate(bal)
            dd = (bal - peak) / np.maximum(peak, 1e-9)
            dds.append(dd.min())
        med_dd = float(np.median(dds))

        # CAGR percentiles
        cagr_p10, cagr_p50, cagr_p90 = np.percentile(r.sim_cagrs, [10, 50, 90])

        return {
            "name": name,
            "group": group,
            "cfg": {k: (list(v) if isinstance(v, (list, tuple, np.ndarray)) else v)
                    for k, v in cfg_kwargs.items() if k != "cashflow"},
            "cf": cf_kwargs,
            "elapsed": round(time.time() - t0, 2),
            "n_sims": r.n_sims,
            "n_years": r.n_years,
            "median_cagr": float(r.median_cagr),
            "cagr_p10": float(cagr_p10),
            "cagr_p90": float(cagr_p90),
            "success_rate": float(r.success_rate),
            "median_final": float(r.median_final_balance),
            "final_p10": float(p10),
            "final_p90": float(p90),
            "swr": float(r.swr),
            "pwr": float(r.pwr),
            "median_vol": med_vol,
            "median_max_dd": med_dd,
            "status": "OK",
            "error": None,
        }
    except Exception as e:
        return {
            "name": name,
            "group": group,
            "cfg": cfg_kwargs,
            "cf": cf_kwargs,
            "elapsed": round(time.time() - t0, 2),
            "status": "ERROR",
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc()[-500:],
        }


BASELINE_ASSETS = [("NIFTY_50", 0.6), ("SBI_GILT", 0.4)]

results = []
counter = [0]


def add(name, group, **kw):
    counter[0] += 1
    tid = f"T{counter[0]:04d}"
    kw.setdefault("assets", BASELINE_ASSETS)
    kw.setdefault("simulations", 500)
    kw.setdefault("years", 30)
    kw.setdefault("seed", 42)
    cf = kw.pop("cf", None)
    r = run_one(f"{tid}_{name}", group, kw, cf)
    results.append(r)
    print(f"{tid} [{group}] {name[:60]:<60} "
          f"{'OK' if r['status']=='OK' else 'ERR'}  "
          f"CAGR={r.get('median_cagr',0):.3f} SR={r.get('success_rate',0):.2f} "
          f"SWR={r.get('swr',0):.3f} MedFin={r.get('median_final',0)/1e6:.1f}M "
          f"({r['elapsed']}s)")


# ============================================================
# GROUP A: Simulation model × distribution
# ============================================================
print("\n=== GROUP A: model variations ===")
for model in [1, 2, 3, 4]:
    for dist in [1, 2]:
        for dof in [5, 10, 30, 50]:
            if model != 3 and dof != 30:
                continue  # dof only matters for model 3
            add(f"model={model}_dist={dist}_dof={dof}", "A_models",
                model=model, distribution_type=dist, degrees_of_freedom=dof)

# ============================================================
# GROUP B: Bootstrap variations
# ============================================================
print("\n=== GROUP B: bootstrap ===")
for bm in [0, 1, 2]:
    for bmin in [1, 3, 5, 10]:
        for bmax in [5, 10, 20]:
            if bmin > bmax:
                continue
            for circ in [True, False]:
                add(f"bm={bm}_min={bmin}_max={bmax}_circ={circ}", "B_bootstrap",
                    model=1, bootstrap_model=bm,
                    bootstrap_min_years=bmin, bootstrap_max_years=bmax,
                    circular_bootstrap=circ)

# ============================================================
# GROUP C: Horizon × sim count × seed
# ============================================================
print("\n=== GROUP C: horizon/sim/seed ===")
for years in [1, 3, 5, 10, 15, 20, 25, 30, 40, 50]:
    for sims in [200, 500, 1000]:
        for seed in [42, 123]:
            add(f"years={years}_sims={sims}_seed={seed}", "C_horizon",
                years=years, simulations=sims, seed=seed)

# ============================================================
# GROUP D: Allocation × asset combos
# ============================================================
print("\n=== GROUP D: allocations ===")
ALLOC_MIXES = [
    [("NIFTY_50", 1.0)],
    [("NIFTY_50", 0.9), ("SBI_GILT", 0.1)],
    [("NIFTY_50", 0.8), ("SBI_GILT", 0.2)],
    [("NIFTY_50", 0.7), ("SBI_GILT", 0.3)],
    [("NIFTY_50", 0.6), ("SBI_GILT", 0.4)],
    [("NIFTY_50", 0.5), ("SBI_GILT", 0.5)],
    [("NIFTY_50", 0.4), ("SBI_GILT", 0.6)],
    [("NIFTY_50", 0.3), ("SBI_GILT", 0.7)],
    [("NIFTY_50", 0.2), ("SBI_GILT", 0.8)],
    [("NIFTY_50", 0.1), ("SBI_GILT", 0.9)],
    [("SBI_GILT", 1.0)],
    [("GOLD", 1.0)],
    [("SBI_LIQUID", 1.0)],
    [("NIFTY_MIDCAP", 1.0)],
    [("NIFTY_BANK", 1.0)],
    [("NIFTY_IT", 1.0)],
    [("NIFTY_50", 0.5), ("GOLD", 0.5)],
    [("NIFTY_50", 0.4), ("SBI_GILT", 0.4), ("GOLD", 0.2)],
    [("NIFTY_50", 0.25), ("SBI_GILT", 0.25), ("GOLD", 0.25), ("SBI_LIQUID", 0.25)],
    [("NIFTY_50", 0.3), ("NIFTY_MIDCAP", 0.3), ("SBI_GILT", 0.4)],
    [("NIFTY_50", 0.6), ("NIFTY_BANK", 0.2), ("SBI_GILT", 0.2)],
]
for assets in ALLOC_MIXES:
    add(f"assets={[(a,round(w,2)) for a,w in assets]}", "D_alloc",
        assets=assets)

# Custom initial balances
for ib in [10_000, 100_000, 1_000_000, 10_000_000, 100_000_000]:
    add(f"initial_bal={ib}", "D_alloc", initial_balance=ib)

# ============================================================
# GROUP E: Cashflow variations
# ============================================================
print("\n=== GROUP E: cashflow ===")

# Contributions (type 1) - SIP
for amt in [5000, 10000, 25000, 50000, 100000]:
    for freq in ["monthly", "quarterly", "annual"]:
        for inf_adj in [True, False]:
            add(f"contrib_{amt}_{freq}_infl={inf_adj}", "E_cashflow",
                cf={"adjustment_type": 1, "amount": amt, "frequency": freq,
                    "inflation_adjusted": inf_adj, "inflation_mean": 0.04})

# Fixed withdrawals (type 2)
for amt in [1000, 5000, 10000, 25000, 50000, 100000, 200000]:
    for freq in ["monthly", "annual"]:
        add(f"wd_{amt}_{freq}", "E_cashflow",
            cf={"adjustment_type": 2, "amount": amt, "frequency": freq,
                "inflation_adjusted": True, "inflation_mean": 0.04})

# Fixed % (type 3)
for pct in [2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]:
    add(f"pct_wd_{pct}", "E_cashflow",
        cf={"adjustment_type": 3, "withdrawal_percentage": pct,
            "frequency": "annual"})

# Life expectancy (type 4)
for age in [40, 55, 65, 75]:
    add(f"life_exp_age={age}", "E_cashflow",
        cf={"adjustment_type": 4, "amount": 30000, "current_age": age,
            "frequency": "annual"})

# Type 8/9 with pct_change
for pct_ch in [-0.05, 0.0, 0.05, 0.10]:
    add(f"t8_wd_pctch={pct_ch}", "E_cashflow",
        cf={"adjustment_type": 8, "amount": 40000, "pct_change": pct_ch,
            "frequency": "annual"})
    add(f"t9_contrib_pctch={pct_ch}", "E_cashflow",
        cf={"adjustment_type": 9, "amount": 12000, "pct_change": pct_ch,
            "frequency": "annual"})

# Stub types 5, 6 (rolling/geometric)
for t in [5, 6]:
    add(f"stub_type_{t}", "E_cashflow",
        cf={"adjustment_type": t, "amount": 40000, "frequency": "annual",
            "withdrawal_percentage": 4.0})

# ============================================================
# GROUP F: Inflation × rebalance × stress
# ============================================================
print("\n=== GROUP F: inflation/rebalance/stress ===")
for infl_adj in [True, False]:
    for infl_mean in [0.0, 0.02, 0.04, 0.06, 0.10, 0.20]:
        add(f"infl_adj={infl_adj}_mean={infl_mean}", "F_inflation",
            inflation_adjusted=infl_adj, inflation_mean=infl_mean)

for rb in [0, 1, 2, 3, 4]:
    add(f"rebalance={rb}", "F_inflation", rebalance_frequency=rb)

for sst in [0, 1, 3, 5, 10]:
    add(f"stress={sst}", "F_inflation", sequence_stress_test=sst)

# Risk-free rate variations
for rf in [0.0, 0.03, 0.05, 0.08, 0.12]:
    add(f"rf={rf}", "F_inflation", risk_free_rate=rf)

# ============================================================
# GROUP G: Adversarial / edge cases
# ============================================================
print("\n=== GROUP G: edge cases ===")

# Extreme withdrawal
add("wd_100k_monthly_20y", "G_edge", years=20,
    cf={"adjustment_type": 2, "amount": 100000, "frequency": "monthly",
        "inflation_adjusted": True, "inflation_mean": 0.04})
add("wd_50pct_annual", "G_edge",
    cf={"adjustment_type": 3, "withdrawal_percentage": 50.0, "frequency": "annual"})
add("wd_100pct_annual", "G_edge",
    cf={"adjustment_type": 3, "withdrawal_percentage": 100.0, "frequency": "annual"})

# Small initial
add("initial_1", "G_edge", initial_balance=1)
add("initial_100", "G_edge", initial_balance=100)

# 100% single volatile
add("100pct_smallcap", "G_edge", assets=[("NIFTY_SMALLCAP", 1.0)])
add("100pct_bank", "G_edge", assets=[("NIFTY_BANK", 1.0)])

# 1 year 10 sims
add("min_sims_years", "G_edge", years=1, simulations=10)

# 50 years max horizon
add("max_horizon", "G_edge", years=50, simulations=1000)

# Parameterized huge vol
add("param_huge_vol_stress", "G_edge",
    model=3, distribution_type=1,
    sequence_stress_test=5)

# GARCH
add("garch_forecasted", "G_edge",
    model=4, time_series_model=3)

# Fat-tailed dof=5
add("fat_tail_dof5", "G_edge",
    model=3, distribution_type=2, degrees_of_freedom=5)

# ============================================================
# SAVE
# ============================================================
print(f"\nTotal tests: {len(results)}")
OUT.write_text(json.dumps(results, indent=2, default=str))
print(f"Saved to {OUT}")

# Quick stats
ok = sum(1 for r in results if r["status"] == "OK")
err = sum(1 for r in results if r["status"] == "ERROR")
print(f"OK: {ok}  ERROR: {err}")

# SWR stats
swrs = [r["swr"] for r in results if r["status"] == "OK"]
print(f"SWR range: {min(swrs):.3f} - {max(swrs):.3f}, mean={np.mean(swrs):.3f}")
sr = [r["success_rate"] for r in results if r["status"] == "OK"]
print(f"Success range: {min(sr):.3f} - {max(sr):.3f}, mean={np.mean(sr):.3f}")

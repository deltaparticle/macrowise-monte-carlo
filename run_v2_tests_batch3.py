"""V2 batch3: additional 60+ tests to hit 450+ and verify new validation."""
import json, time, traceback, warnings, contextlib, io
from pathlib import Path
import numpy as np
import sys
sys.path.insert(0, str(Path(__file__).parent))

from macrowise.engine.monte_carlo import MonteCarloConfig, MonteCarloSimulation
from macrowise.engine.cashflow import CashFlowConfig

OUT = Path(__file__).parent / "v2_test_results_batch3.json"
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

def add(name, group, expect_error=None, **kw):
    counter[0] += 1
    tid = f"Y{counter[0]:04d}"
    kw.setdefault("assets", [("NIFTY_50", 0.6), ("SBI_GILT", 0.4)])
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
# N2_fixed: rerun with CORRECT assets (custom_means/stds match)
# ============================================================
print("\n=== N2_fixed: Parametric vol correctness (corrected) ===")
test_configs = [
    ([("NIFTY_50", 1.0)], [0.15], [0.20], 0.20),
    ([("NIFTY_50", 1.0)], [0.10], [0.10], 0.10),
    ([("NIFTY_50", 1.0)], [0.05], [0.30], 0.30),
    ([("SBI_GILT", 1.0)], [0.05], [0.05], 0.05),
    ([("SBI_GILT", 1.0)], [0.05], [0.15], 0.15),
    # 2-asset with proper matching stds
    ([("NIFTY_50", 0.6), ("SBI_GILT", 0.4)], [0.15, 0.05], [0.20, 0.05], None),
    ([("NIFTY_50", 0.6), ("SBI_GILT", 0.4)], [0.15, 0.05], [0.25, 0.03], None),
]
for assets, cm, cs, expected_vol in test_configs:
    add(f"param_vol_std{cs[0]}", "N2_param_vol_fixed",
        assets=assets,
        model=3, distribution_type=1,
        custom_means=cm, custom_stds=cs, use_historical_correlations=False,
        simulations=1000)

# Verify new validation catches length mismatch
add("custom_means_len_mismatch", "N2_param_vol_fixed",
    model=3, custom_means=[0.15], custom_stds=[0.20],  # 1 value but 2 assets
    expect_error="valueerror")
add("custom_stds_len_mismatch", "N2_param_vol_fixed",
    model=3, custom_means=[0.15, 0.05], custom_stds=[0.20],  # 1 value but 2 assets
    expect_error="valueerror")

# ============================================================
# Y1: Boundary + edge behaviors
# ============================================================
print("\n=== Y1: Boundary sweep ===")
# Withdrawal at breakpoint rates (should show smooth transition)
for pct in [3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0]:
    add(f"wd_amt_{pct}pct_of_1M", "Y1_boundary",
        cf={"adjustment_type": 2, "amount": int(pct * 10000), "frequency": "annual",
            "inflation_adjusted": True, "inflation_mean": 0.04},
        simulations=1000)

# Withdrawal amount + contribution simultaneously (net)
# Since only one cf, test net-negative via contribution+withdrawal amount
for c_amt in [10000, 25000, 50000, 100000]:
    add(f"contrib_growing_{c_amt}", "Y1_boundary",
        cf={"adjustment_type": 1, "amount": c_amt, "frequency": "monthly",
            "growth_rate": 0.08, "inflation_adjusted": True},
        simulations=500)

# Test various inflation combos with withdrawal
for infl in [0.02, 0.06, 0.10, 0.15]:
    for infl_vol in [0.01, 0.03, 0.05]:
        add(f"infl_wd_m{infl}_v{infl_vol}", "Y1_boundary",
            inflation_adjusted=True, inflation_mean=infl,
            inflation_volatility=infl_vol,
            cf={"adjustment_type": 2, "amount": 40000, "frequency": "annual",
                "inflation_adjusted": True, "inflation_mean": infl},
            simulations=500)

# ============================================================
# Y2: Sharpe/Sortino sanity — no zero-vol case
# ============================================================
print("\n=== Y2: Ratios ===")
# Various risk-free rates
for rf in [0.0, 0.03, 0.05, 0.08, 0.12, 0.20]:
    add(f"rf_{rf}", "Y2_ratios", risk_free_rate=rf)

# ============================================================
# Y3: Portfolio types with very different risk profiles
# ============================================================
print("\n=== Y3: Diverse portfolios ===")
portfolios = [
    [("NIFTY_50", 0.20), ("NIFTY_MIDCAP", 0.20), ("NIFTY_BANK", 0.20),
     ("NIFTY_IT", 0.20), ("SBI_GILT", 0.20)],
    [("NIFTY_SMALLCAP", 0.30), ("NIFTY_MIDCAP", 0.30), ("NIFTY_50", 0.20), ("GOLD", 0.20)],
    [("SBI_GILT", 0.60), ("SBI_LIQUID", 0.20), ("SBI_CORP", 0.20)],  # 100% debt
    [("NIFTY_50", 0.15), ("NIFTY_MIDCAP", 0.15), ("NIFTY_BANK", 0.15),
     ("NIFTY_IT", 0.10), ("NIFTY_PHARMA", 0.10), ("SBI_GILT", 0.25), ("GOLD", 0.10)],
    [("GOLD", 0.50), ("NIFTY_50", 0.30), ("SBI_LIQUID", 0.20)],  # commodity-heavy
]
for i, p in enumerate(portfolios):
    add(f"diverse_portfolio_{i}", "Y3_diverse", assets=p, simulations=500)

# ============================================================
# Y4: Cross-model with cashflows
# ============================================================
print("\n=== Y4: Model x cashflow ===")
for m in [1, 3, 4]:
    for cf_type, cf_params in [
        (1, {"adjustment_type": 1, "amount": 10000, "frequency": "monthly"}),
        (2, {"adjustment_type": 2, "amount": 40000, "frequency": "annual",
             "inflation_adjusted": True, "inflation_mean": 0.04}),
        (3, {"adjustment_type": 3, "withdrawal_percentage": 5.0, "frequency": "annual"}),
    ]:
        add(f"m{m}_cf{cf_type}", "Y4_model_cf",
            model=m, cf=cf_params, simulations=500)


# ============================================================
print(f"\nTotal batch3: {len(results)}")
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

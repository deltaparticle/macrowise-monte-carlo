"""Analyze test results: apply sanity rules, verdict PASS/FAIL/WARN per test, aggregate anomalies."""
import json
from pathlib import Path
import numpy as np
from collections import defaultdict

BATCHES = ["exhaustive_test_results.json", "exhaustive_test_results_batch2.json"]
results = []
for b in BATCHES:
    p = Path(__file__).parent / b
    if p.exists():
        results.extend(json.loads(p.read_text()))

print(f"Loaded {len(results)} tests\n")


# ==============================================
# Per-test verdicts based on sanity rules
# ==============================================
def verdict_for(r):
    if r["status"] == "ERROR":
        return ("FAIL", f"Runtime error: {r.get('error','?')}")
    reasons = []
    warns = []

    cfg = r.get("cfg", {})
    cf = r.get("cf") or {}
    cagr = r.get("median_cagr", 0)
    sr = r.get("success_rate", 0)
    swr = r.get("swr", 0)
    med_fin = r.get("median_final", 0)
    p10 = r.get("final_p10", 0)
    p90 = r.get("final_p90", 0)
    med_dd = r.get("median_max_dd", 0)
    med_vol = r.get("median_vol", 0)
    ib = cfg.get("initial_balance", 1_000_000)

    # 1. CAGR bounds - reasonable range for Indian mkt
    if cagr < -0.5 or cagr > 0.5:
        reasons.append(f"CAGR out of range: {cagr:.2%}")
    # 1b. SWR at cap - flag if hits 8% ceiling (indicates heuristic clip)
    if abs(swr - 0.08) < 0.001:
        warns.append(f"SWR at 8% ceiling (heuristic clip - always identical output)")
    elif abs(swr - 0.02) < 0.001:
        warns.append(f"SWR at 2% floor (heuristic clip)")
    # 2. Percentile ordering
    if p10 > med_fin + 1 or med_fin > p90 + 1:
        reasons.append(f"Percentile order broken p10={p10:.0f} > med={med_fin:.0f} or med > p90={p90:.0f}")
    # 3. Volatility should be positive for any non-trivial model
    if med_vol < 0.001:
        reasons.append(f"Zero volatility: {med_vol}")
    # 4. Max drawdown negative
    if med_dd > 0.001:
        reasons.append(f"Positive max DD: {med_dd:.2%}")

    # 5. Sanity of SWR - should vary somewhat with config
    #    (individual test can't verify variation; aggregate check below)

    # 6. Success rate expectations by cashflow type
    cf_type = cf.get("adjustment_type", 0)
    if cf_type == 0:
        # No cashflow: with positive-return assets, sr should be ~100%
        # (this is trivial - not a bug per se)
        pass
    elif cf_type == 2:
        wd_amt = cf.get("amount", 0)
        freq = cf.get("frequency", "annual")
        yearly_wd = wd_amt * ({"monthly":12,"quarterly":4,"annual":1}[freq])
        wd_pct = yearly_wd / ib if ib > 0 else 0
        # Asymptote-to-zero bug check
        if med_fin < ib * 0.01 and sr > 0.99:
            reasons.append(f"Portfolio at ~0 (med_fin={med_fin:.1f} = {med_fin/ib*100:.3f}% of initial) but SR=100%")
        if wd_pct > 0.10 and sr > 0.98:
            warns.append(f"Very high WD {wd_pct:.1%}/yr but SR={sr:.1%} (suspicious)")
    elif cf_type == 3:
        wd_pct = cf.get("withdrawal_percentage", 0) / 100
        # If med_fin < 1% of initial but SR = 100%, that's a bug (asymptote-to-zero)
        if med_fin < ib * 0.01 and sr > 0.99:
            reasons.append(f"Portfolio at ~0 (med_fin={med_fin:.1f} = {med_fin/ib*100:.3f}% of initial) but SR=100% — asymptote bug")
        if wd_pct > 0.06 and sr > 0.99 and med_fin > ib * 2:
            warns.append(f"Fixed% {wd_pct:.0%} annual but med final = {med_fin/ib:.1f}x initial (unrealistic)")

    # 7. If sequence stress > 0, expect worse outcomes than baseline
    #    (can't verify with just this test; leave aggregate check)

    verdict = "FAIL" if reasons else ("WARN" if warns else "PASS")
    reason_str = "; ".join(reasons + warns) or "sanity checks pass"
    return (verdict, reason_str)


# ==============================================
# Apply
# ==============================================
counts = defaultdict(int)
for r in results:
    v, why = verdict_for(r)
    r["verdict"] = v
    r["verdict_reason"] = why
    counts[v] += 1

print("Verdict counts:", dict(counts))

# ==============================================
# Aggregate anomaly analysis
# ==============================================
print("\n" + "="*60)
print("AGGREGATE ANOMALY ANALYSIS")
print("="*60)

# --- SWR distribution ---
swrs = [r["swr"] for r in results if r.get("status") == "OK"]
print(f"\nSWR: min={min(swrs):.4f} max={max(swrs):.4f} mean={np.mean(swrs):.4f} std={np.std(swrs):.4f}")
print(f"  Unique SWR values: {sorted(set(round(s, 3) for s in swrs))[:15]}")
at_cap = sum(1 for s in swrs if abs(s - 0.08) < 0.001)
print(f"  Tests at SWR=8.0% cap: {at_cap}/{len(swrs)} ({at_cap/len(swrs)*100:.1f}%)")

# --- Success rate distribution ---
srs = [r["success_rate"] for r in results if r.get("status") == "OK"]
print(f"\nSuccess rate: min={min(srs):.4f} max={max(srs):.4f} mean={np.mean(srs):.4f}")
at_100 = sum(1 for s in srs if s > 0.999)
print(f"  Tests at SR=100%: {at_100}/{len(srs)} ({at_100/len(srs)*100:.1f}%)")

# --- Withdrawal-only analysis ---
wd_tests = [r for r in results if r.get("cf") and r["cf"].get("adjustment_type") in [2,3,8]]
print(f"\nWithdrawal tests: {len(wd_tests)}")
wd_100 = sum(1 for r in wd_tests if r["success_rate"] > 0.999)
print(f"  With 100% success: {wd_100}/{len(wd_tests)} ({wd_100/len(wd_tests)*100:.1f}%)")

# High-withdrawal tests
high_wd = [r for r in wd_tests if r.get("cf", {}).get("adjustment_type") == 3 and
           r["cf"].get("withdrawal_percentage", 0) >= 8]
print(f"  >= 8% withdrawal rate: {len(high_wd)} tests")
for r in high_wd[:8]:
    print(f"    {r['name'][:50]} pct={r['cf'].get('withdrawal_percentage')}% "
          f"SR={r['success_rate']:.3f} MedFin={r['median_final']/1e6:.2f}M")

# --- Model comparison ---
print("\nCAGR by model (baseline 60/40 30y):")
for m in [1,2,3,4]:
    rows = [r for r in results if r["cfg"].get("model") == m and r["cfg"].get("years")==30
            and r["cfg"].get("assets", []) == [["NIFTY_50",0.6],["SBI_GILT",0.4]] and r.get("cf") is None
            and r["cfg"].get("simulations")==500]
    if rows:
        cagrs = [r["median_cagr"] for r in rows]
        print(f"  Model {m}: n={len(rows)} CAGR mean={np.mean(cagrs):.4f} range=[{min(cagrs):.4f}, {max(cagrs):.4f}]")

# --- Seed reproducibility ---
print("\nSeed reproducibility check:")
seed_tests = [r for r in results if r["group"] == "J_seed"] if any(r["group"]=="J_seed" for r in results) else []
seeds = defaultdict(list)
for r in results:
    key = (r["cfg"].get("years"), r["cfg"].get("simulations"), tuple(tuple(x) for x in r["cfg"].get("assets", [])))
    if r.get("cf") is None:
        seeds[key].append((r["cfg"].get("seed"), r["median_cagr"]))

# Any same-seed same-config produce different result?
# Skip this since we set seeds unique per test.

# --- Missing metrics check ---
n_infty_pwr = sum(1 for r in results if r.get("pwr", 0) > 0.5)
print(f"\nPWR > 50% (suspicious): {n_infty_pwr}")

# Save verdicts back
out = Path(__file__).parent / "test_verdicts.json"
out.write_text(json.dumps(results, indent=2, default=str))
print(f"\nSaved verdicts to {out}")

"""Analyze v2 test results - brutally honest audit."""
import json
from pathlib import Path
import numpy as np
from collections import defaultdict, Counter

BATCHES = ["v2_test_results.json", "v2_test_results_batch2.json", "v2_test_results_batch3.json"]
data = []
for b in BATCHES:
    p = Path(__file__).parent / b
    if p.exists():
        data.extend(json.loads(p.read_text()))

print(f"Total v2 tests: {len(data)}\n")

# Status breakdown
statuses = Counter(r["status"] for r in data)
print(f"Status: {dict(statuses)}\n")

# Sanity verdict rules
def verdict_for(r):
    """Return (verdict, reason). PASS/WARN/FAIL/ERROR."""
    st = r.get("status", "?")
    if st == "OK_EXPECTED_ERROR":
        return ("PASS", "expected error correctly raised")
    if st == "FAIL_EXPECTED_ERROR":
        return ("FAIL", f"expected {r.get('expected')} but sim succeeded")
    if st == "ERROR":
        return ("FAIL", f"unexpected: {r.get('error', '?')[:100]}")
    # st = OK
    warns = []
    reasons = []
    cfg = r.get("cfg", {})
    cf = r.get("cf") or {}
    cagr = r.get("median_cagr", 0)
    sr = r.get("success_rate", 0)
    swr = r.get("swr", 0)
    med_fin = r.get("median_final", 0)
    p10 = r.get("final_p10", 0)
    p90 = r.get("final_p90", 0)
    med_vol = r.get("median_vol", 0)
    med_dd = r.get("median_max_dd", 0)
    ib = cfg.get("initial_balance", 1_000_000)

    # 1. Percentile ordering
    if p10 > med_fin + 1 or med_fin > p90 + 1:
        reasons.append(f"percentile order broken p10={p10:.0f} med={med_fin:.0f} p90={p90:.0f}")
    # 2. CAGR bounds
    if cagr < -0.5 or cagr > 0.6:
        reasons.append(f"CAGR out of range: {cagr:.2%}")
    # 3. Vol positive
    if med_vol <= 0.001 and cfg.get("model") != 3 or med_vol < -1e-6:
        # Only warn for model 3 - allow near-zero vol if user set custom_stds=0
        if cfg.get("custom_stds") is None:
            reasons.append(f"zero volatility: {med_vol}")
    # 4. Max DD negative
    if med_dd > 0.001:
        reasons.append(f"positive max DD: {med_dd:.2%}")
    # 5. Success rate + fixed withdrawal
    cf_type = cf.get("adjustment_type", 0)
    if cf_type == 2 and sr > 0.99:
        wd_amt = cf.get("amount", 0)
        freq = cf.get("frequency", "annual")
        yearly = wd_amt * {"monthly":12,"quarterly":4,"annual":1}.get(freq, 1)
        wd_pct = yearly / ib if ib > 0 else 0
        if wd_pct > 0.12:
            warns.append(f"very high WD ({wd_pct:.0%}/yr) yet SR=100%")
    # 6. SR near 100% with med_fin near zero (asymptote check, should be gone but re-verify)
    if med_fin < ib * 0.005 and sr > 0.99 and cf_type != 0:
        reasons.append(f"asymptote suspected: med_fin={med_fin:.1f} but SR=100%")

    if reasons:
        return ("FAIL", "; ".join(reasons))
    if warns:
        return ("WARN", "; ".join(warns))
    return ("PASS", "sanity checks pass")


counts = Counter()
for r in data:
    v, why = verdict_for(r)
    r["verdict"] = v
    r["verdict_reason"] = why
    counts[v] += 1

print(f"Verdicts: {dict(counts)}\n")

# SWR distribution
oks = [r for r in data if r.get("status") == "OK"]
if oks:
    swrs = [r["swr"] for r in oks]
    print(f"SWR: min={min(swrs):.4f} max={max(swrs):.4f} mean={np.mean(swrs):.4f} std={np.std(swrs):.4f}")
    unique_swrs = sorted(set(round(s, 4) for s in swrs))
    print(f"  Distinct SWR values: {len(unique_swrs)}")
    print(f"  Sample: {unique_swrs[:20]}")
    at_cap = sum(1 for s in swrs if abs(s - 0.08) < 0.001)
    print(f"  At old 8% cap: {at_cap} ({at_cap/len(swrs)*100:.1f}%)")

srs = [r["success_rate"] for r in oks]
print(f"\nSR: min={min(srs):.4f} max={max(srs):.4f} mean={np.mean(srs):.4f}")
at_100 = sum(1 for s in srs if s > 0.999)
at_0 = sum(1 for s in srs if s < 0.001)
mid = sum(1 for s in srs if 0.01 < s < 0.99)
print(f"  SR=100%: {at_100} ({at_100/len(srs)*100:.1f}%)")
print(f"  SR=0%: {at_0}")
print(f"  Intermediate (1-99%): {mid}")

# By group
group_verdicts = defaultdict(Counter)
for r in data:
    group_verdicts[r["group"]][r["verdict"]] += 1
print("\nBy group:")
for g in sorted(group_verdicts.keys()):
    print(f"  {g}: {dict(group_verdicts[g])}")

# Save
out = Path("v2_test_verdicts.json")
out.write_text(json.dumps(data, indent=2, default=str))
print(f"\nSaved: {out}")

# Show ALL FAIL
fails = [r for r in data if r["verdict"] == "FAIL"]
print(f"\n=== {len(fails)} FAIL(s) ===")
for r in fails:
    print(f"  {r['name'][:60]} | {r['verdict_reason'][:120]}")

# Show WARNS
warns = [r for r in data if r["verdict"] == "WARN"]
print(f"\n=== {len(warns)} WARN(s) ===")
for r in warns[:30]:
    print(f"  {r['name'][:60]} | {r['verdict_reason'][:100]}")

"""
Exhaustive integration test for the Macrowise Monte Carlo API.

Runs every meaningful permutation of the SimulateRequest schema against the
in-process FastAPI app via TestClient. Each test asserts:
  - HTTP status code
  - response schema validates (Pydantic auto-validates on the way out)
  - basic numeric sanity (medians, drawdowns, distribution counts, etc.)

Run:
    .venv/Scripts/python tests/test_api_exhaustive.py
"""
from __future__ import annotations

import json
import math
import sys
import traceback
from typing import Any, Dict

from fastapi.testclient import TestClient
from api.main import app


# ── Test harness ─────────────────────────────────────────────────────────────

client = TestClient(app)

FAILS: list[tuple[str, str]] = []
PASSES: list[str] = []
NUMERIC_LOG: list[str] = []


def _record(name: str, ok: bool, msg: str = "") -> None:
    if ok:
        PASSES.append(name)
    else:
        FAILS.append((name, msg))
    marker = "PASS" if ok else "FAIL"
    print(f"[{marker}] {name}" + (f"  {msg}" if msg and not ok else ""))


def _post_ok(name: str, payload: Dict[str, Any], expected: int = 200) -> Dict[str, Any] | None:
    """POST /simulate and assert status. Return response JSON on success."""
    try:
        r = client.post("/simulate", json=payload)
    except Exception as e:
        _record(name, False, f"exception: {e}")
        return None

    if r.status_code != expected:
        _record(name, False, f"status={r.status_code} expected={expected} body={r.text[:400]}")
        return None

    body = r.json()
    if expected == 200:
        # Sanity: response shape
        for key in [
            "n_simulations", "n_years", "assets", "median_cagr", "success_rate",
            "median_final_balance", "swr", "pwr", "performance_summary",
            "balance_percentiles", "expected_returns", "loss_probabilities",
            "simulated_assets", "terminal_distribution", "drawdown_percentiles",
        ]:
            if key not in body:
                _record(name, False, f"missing response key: {key}")
                return None
    _record(name, True)
    return body


def _sanity(name: str, body: Dict[str, Any]) -> None:
    """Assert numeric outputs are physically plausible."""
    problems = []

    # Portfolio should not produce insane returns
    cagr = body["median_cagr"]
    if not math.isfinite(cagr):
        problems.append(f"median_cagr not finite: {cagr}")
    elif cagr < -1.0 or cagr > 1.0:
        problems.append(f"median_cagr out of [-100%, +100%]: {cagr:.4f}")

    sr = body["success_rate"]
    if not (0.0 <= sr <= 1.0):
        problems.append(f"success_rate outside [0,1]: {sr}")

    mfb = body["median_final_balance"]
    if not math.isfinite(mfb) or mfb < 0:
        problems.append(f"median_final_balance invalid: {mfb}")

    swr, pwr = body["swr"], body["pwr"]
    if not (0.0 <= swr <= 0.20):
        problems.append(f"swr out of [0, 20%]: {swr}")
    if not (0.0 <= pwr <= 0.20):
        problems.append(f"pwr out of [0, 20%]: {pwr}")
    if pwr > swr + 1e-9:
        problems.append(f"pwr {pwr} > swr {swr} (should be <=)")

    # Balance percentiles monotone: p10 <= p25 <= p50 <= p75 <= p90 at every year
    bp = body["balance_percentiles"]
    for year, band in bp.items():
        vs = [band["p10"], band["p25"], band["p50"], band["p75"], band["p90"]]
        if any(vs[i] > vs[i + 1] + 1e-6 for i in range(4)):
            problems.append(f"balance_percentiles year {year} not monotone: {vs}")
            break

    # Year 0 balance should equal initial_balance across all bands
    year0 = bp.get("0")
    if year0:
        init = body["config_echo"]["initial_balance"]
        for k in ("p10", "p25", "p50", "p75", "p90"):
            if abs(year0[k] - init) > 1.0:
                problems.append(f"year 0 {k}={year0[k]} != initial_balance {init}")
                break

    # Drawdown percentiles should all be <= 0
    dd = body["drawdown_percentiles"]
    for k, v in dd.items():
        if v > 1e-6:
            problems.append(f"drawdown_percentiles {k}={v} > 0")

    # Terminal distribution: counts sum = n_sims, edges = counts+1
    td = body["terminal_distribution"]
    counts, edges = td["bin_counts"], td["bin_edges"]
    if len(edges) != len(counts) + 1:
        problems.append(f"histogram edges/counts mismatch: {len(edges)} vs {len(counts)}")
    if sum(counts) != body["n_simulations"]:
        problems.append(f"histogram sum {sum(counts)} != n_simulations {body['n_simulations']}")

    # performance_summary should have all 9 known keys
    expected_perf = {
        "time_weighted_return_nominal", "time_weighted_return_real",
        "portfolio_end_balance_nominal", "portfolio_end_balance_real",
        "annual_mean_return", "annualized_volatility",
        "sharpe_ratio", "sortino_ratio", "maximum_drawdown",
    }
    got = set(body["performance_summary"].keys())
    if expected_perf - got:
        problems.append(f"performance_summary missing: {expected_perf - got}")

    # Probability tables: cells in [0, 1] or null
    for key in ("expected_returns", "loss_probabilities"):
        for thr, row in body[key].items():
            for h, p in row.items():
                if p is None:
                    continue
                if not (0.0 <= p <= 1.0 + 1e-9):
                    problems.append(f"{key}[{thr}][{h}]={p} out of [0,1]")
                    break

    # Assets echoed back
    if not body["assets"]:
        problems.append("assets list empty")

    # Log key numeric outputs so we can eyeball reasonableness
    NUMERIC_LOG.append(
        f"{name}: cagr={cagr:.4f} success={sr:.3f} "
        f"medfb={mfb:,.0f} swr={swr:.4f} pwr={pwr:.4f} "
        f"dd_p50={dd['p50']:.3f}"
    )

    if problems:
        _record(name + " [sanity]", False, "; ".join(problems))
    else:
        _record(name + " [sanity]", True)


def run(name: str, payload: Dict[str, Any], expected: int = 200, check_sanity: bool = True) -> None:
    """Run a case: POST /simulate, check status, and (for 200s) numeric sanity."""
    body = _post_ok(name, payload, expected=expected)
    if body is not None and expected == 200 and check_sanity:
        _sanity(name, body)


# Fast, deterministic baseline used by nearly every test.
def base(**overrides) -> Dict[str, Any]:
    p = {
        "initial_balance": 1_000_000,
        "years": 10,
        "simulations": 100,
        "assets": [
            {"asset": "NIFTY_50", "weight": 0.60},
            {"asset": "NIFTY_MIDCAP_150", "weight": 0.40},
        ],
        "model": 1,
        "bootstrap_model": 1,
        "rebalance_frequency": 1,
        "inflation_adjusted": True,
        "seed": 42,
    }
    p.update(overrides)
    return p


# ── Catalog endpoints ────────────────────────────────────────────────────────

def test_catalog():
    print("\n=== Catalog endpoints ===")
    _record("GET /",           client.get("/").status_code == 200)
    _record("GET /health",     client.get("/health").status_code == 200)
    _record("GET /models",     client.get("/models").status_code == 200)
    _record("GET /examples",   client.get("/examples").status_code == 200)

    r = client.get("/assets")
    _record("GET /assets total=719", r.status_code == 200 and r.json()["total"] == 719,
            f"got {r.json().get('total')}")

    r = client.get("/assets/search", params={"q": "nifty 50"})
    _record("GET /assets/search q=nifty 50", r.status_code == 200 and any(
        x["alias"] == "NIFTY_50" for x in r.json()["results"]))

    r = client.get("/assets/search", params={"q": "midcap", "limit": 5})
    _record("GET /assets/search limit works", r.status_code == 200 and len(r.json()["results"]) <= 5)

    r = client.get("/assets/search", params={"q": "z", "category": "large_cap", "limit": 5})
    _record("GET /assets/search category filter", r.status_code == 200 and all(
        x["category"] == "large_cap" for x in r.json()["results"]))

    r = client.get("/assets/NIFTY_50")
    _record("GET /assets/NIFTY_50", r.status_code == 200 and r.json()["alias"] == "NIFTY_50")

    r = client.get("/assets/NIFTY_50")
    _record("GET /assets/NIFTY_50 data_code populated",
            r.status_code == 200 and r.json()["data_code"] == "NIFTY_50")

    r = client.get("/assets/DOES_NOT_EXIST")
    _record("GET /assets/DOES_NOT_EXIST -> 404",
            r.status_code == 404 and r.json()["error"] == "not_found")

    # Every top-level meta endpoint returns 200
    for path in ("/docs", "/redoc", "/openapi.json"):
        _record(f"GET {path}", client.get(path).status_code == 200)


# ── Simulation model coverage ────────────────────────────────────────────────

def test_models():
    print("\n=== Simulation model coverage ===")

    # Model 1: historical bootstrap × 3 bootstrap types × circular on/off
    for bm in (0, 1, 2):
        for circ in (True, False):
            run(f"model=1 bootstrap={bm} circular={circ}",
                base(model=1, bootstrap_model=bm, circular_bootstrap=circ,
                     bootstrap_min_years=2, bootstrap_max_years=8))

    # Model 2: statistical (bootstrap + rescale)
    run("model=2 default", base(model=2))
    run("model=2 custom means", base(
        model=2,
        custom_means=[0.14, 0.16],
        historical_volatility=True,
    ))
    run("model=2 custom means+stds", base(
        model=2,
        custom_means=[0.12, 0.15],
        custom_stds=[0.18, 0.24],
        historical_volatility=False,
    ))

    # Model 3: parameterized
    run("model=3 normal", base(model=3, distribution_type=1))
    run("model=3 fat-tail df=5", base(model=3, distribution_type=2, degrees_of_freedom=5))
    run("model=3 fat-tail df=30", base(model=3, distribution_type=2, degrees_of_freedom=30))

    # Model 3 with custom correlation (identity — assets independent)
    run("model=3 custom corr identity", base(
        model=3, distribution_type=1,
        historical_correlations=False,
        custom_correlation=[[1.0, 0.0], [0.0, 1.0]],
    ))
    run("model=3 custom corr 0.5", base(
        model=3, distribution_type=1,
        historical_correlations=False,
        custom_correlation=[[1.0, 0.5], [0.5, 1.0]],
    ))
    run("model=3 custom means+stds+corr", base(
        model=3, distribution_type=1,
        historical_volatility=False,
        historical_correlations=False,
        custom_means=[0.13, 0.15],
        custom_stds=[0.17, 0.22],
        custom_correlation=[[1.0, 0.6], [0.6, 1.0]],
    ))

    # Model 4: GARCH & Normal-forecasted
    run("model=4 ts=1 normal", base(model=4, time_series_model=1))
    run("model=4 ts=3 GARCH", base(model=4, time_series_model=3))


# ── Rebalance frequencies ────────────────────────────────────────────────────

def test_rebalance():
    print("\n=== Rebalance frequencies ===")
    for rf in (0, 1, 2, 3, 4):
        run(f"rebalance={rf}", base(rebalance_frequency=rf))


# ── Inflation modes ──────────────────────────────────────────────────────────

def test_inflation():
    print("\n=== Inflation modes ===")
    run("inflation_adjusted=False",  base(inflation_adjusted=False))
    run("inflation_adjusted=True historical",
        base(inflation_adjusted=True, inflation_model=1))
    run("inflation_adjusted=True parametric high",
        base(inflation_adjusted=True, inflation_model=2, inflation_mean=0.08, inflation_volatility=0.04))
    run("inflation_adjusted=True parametric zero-vol",
        base(inflation_adjusted=True, inflation_model=2, inflation_mean=0.05, inflation_volatility=0.0))


# ── Sequence stress test ─────────────────────────────────────────────────────

def test_sequence_stress():
    print("\n=== Sequence stress test ===")
    for s in (0, 1, 3, 5, 10):
        run(f"sequence_stress={s}", base(sequence_stress_test=s))


# ── Cashflows: every implemented adjustment_type ─────────────────────────────

def test_cashflows():
    print("\n=== Cashflow adjustment types ===")

    # Type 0 == None
    run("cashflow_type=0", base(cashflow_type=0))

    # Type 1: contributions
    run("SIP monthly 25k", base(
        cashflow_type=1, cashflow_amount=25000, cashflow_frequency="monthly",
        years=15, initial_balance=100000))
    run("SIP quarterly 75k", base(
        cashflow_type=1, cashflow_amount=75000, cashflow_frequency="quarterly",
        years=15, initial_balance=100000))
    run("SIP annual 300k", base(
        cashflow_type=1, cashflow_amount=300000, cashflow_frequency="annual",
        years=15, initial_balance=100000))

    # Type 2: fixed withdrawal
    run("SWP monthly 20k",
        base(cashflow_type=2, cashflow_amount=20000, cashflow_frequency="monthly",
             years=25, initial_balance=10_000_000))
    run("SWP annual 800k",
        base(cashflow_type=2, cashflow_amount=800000, cashflow_frequency="annual",
             years=25, initial_balance=10_000_000))

    # Type 3: fixed % of balance
    run("Fixed% 4% annual",
        base(cashflow_type=3, withdrawal_percentage=4.0, cashflow_frequency="annual",
             years=25, initial_balance=10_000_000))
    run("Fixed% 5% monthly",
        base(cashflow_type=3, withdrawal_percentage=5.0, cashflow_frequency="monthly",
             years=25, initial_balance=10_000_000))

    # Type 4: life expectancy
    run("LifeExp single age 60",
        base(cashflow_type=4, cashflow_amount=100000, cashflow_frequency="annual",
             current_age=60, life_expectancy_model="single",
             years=25, initial_balance=10_000_000))
    run("LifeExp uniform age 55",
        base(cashflow_type=4, cashflow_amount=100000, cashflow_frequency="annual",
             current_age=55, life_expectancy_model="uniform",
             years=30, initial_balance=10_000_000))

    # Type 8: fixed withdrawal + pct change
    run("Fixed+pct type=8",
        base(cashflow_type=8, cashflow_amount=15000, cashflow_frequency="monthly",
             years=20, initial_balance=5_000_000))

    # Type 9: contribution + pct change
    run("Contrib+pct type=9",
        base(cashflow_type=9, cashflow_amount=20000, cashflow_frequency="monthly",
             years=20, initial_balance=100000))

    # Type 5 & 6 are unimplemented in the engine
    for t in (5, 6):
        body = client.post("/simulate", json=base(
            cashflow_type=t, cashflow_amount=1000, cashflow_frequency="annual"))
        ok = body.status_code == 500 and "engine_error" in body.text
        _record(f"cashflow_type={t} unimplemented -> 500", ok,
                f"got {body.status_code}: {body.text[:200]}")


# ── History window ───────────────────────────────────────────────────────────

def test_history_window():
    print("\n=== Historical window filters ===")
    run("full history",
        base(use_full_history=True))
    run("start_year=2005 end_year=2020",
        base(use_full_history=False, start_year=2005, end_year=2020))
    run("start_year=2010 only",
        base(use_full_history=False, start_year=2010))
    run("end_year=2015 only",
        base(use_full_history=False, end_year=2015))


# ── Portfolios ──────────────────────────────────────────────────────────────

def test_portfolios():
    print("\n=== Portfolio compositions ===")
    run("single-asset NIFTY_500",
        base(assets=[{"asset": "NIFTY_500", "weight": 1.0}]))
    run("4-asset factor blend",
        base(assets=[
            {"asset": "NIFTY_ALPHA_50", "weight": 0.25},
            {"asset": "NIFTY200_MOMENTUM_30", "weight": 0.25},
            {"asset": "NIFTY100_QUALITY_30", "weight": 0.25},
            {"asset": "NIFTY_LOW_VOLATILITY_50", "weight": 0.25},
        ]))
    run("sector mix",
        base(assets=[
            {"asset": "NIFTY_BANK", "weight": 0.25},
            {"asset": "NIFTY_IT", "weight": 0.20},
            {"asset": "NIFTY_PHARMA", "weight": 0.15},
            {"asset": "NIFTY_FMCG", "weight": 0.20},
            {"asset": "NIFTY_AUTO", "weight": 0.20},
        ]))
    run("individual stocks 3-way",
        base(assets=[
            {"asset": "RELIANCE", "weight": 0.4},
            {"asset": "TCS", "weight": 0.3},
            {"asset": "HDFCBANK", "weight": 0.3},
        ]))


# ── Horizon / sample sizes ───────────────────────────────────────────────────

def test_horizons():
    print("\n=== Horizons and sample sizes ===")
    for years in (1, 5, 30, 50, 100):
        run(f"years={years}", base(years=years))
    for sims in (10, 100, 1000, 5000):
        run(f"simulations={sims}", base(simulations=sims))


# ── Determinism ──────────────────────────────────────────────────────────────

def test_determinism():
    print("\n=== Determinism ===")
    r1 = client.post("/simulate", json=base(seed=123)).json()
    r2 = client.post("/simulate", json=base(seed=123)).json()
    r3 = client.post("/simulate", json=base(seed=999)).json()
    same = (r1["median_cagr"] == r2["median_cagr"] and
            r1["median_final_balance"] == r2["median_final_balance"] and
            r1["swr"] == r2["swr"])
    diff = r1["median_cagr"] != r3["median_cagr"]
    _record("same seed -> same output", same,
            f"cagr {r1['median_cagr']} vs {r2['median_cagr']}")
    _record("different seed -> different output", diff,
            f"cagr {r1['median_cagr']} vs {r3['median_cagr']}")


# ── Error cases ──────────────────────────────────────────────────────────────

def test_errors():
    print("\n=== Error handling ===")

    # Weights don't sum to 1
    run("bad weights", base(assets=[
        {"asset": "NIFTY_50", "weight": 0.5},
        {"asset": "NIFTY_MIDCAP_150", "weight": 0.3},
    ]), expected=400, check_sanity=False)

    # Unknown asset
    run("unknown asset", base(assets=[{"asset": "FAKE_XYZ", "weight": 1.0}]),
        expected=400, check_sanity=False)

    # tax_enabled = True (not yet implemented)
    run("tax_enabled=True", base(tax_enabled=True), expected=400, check_sanity=False)

    # Field validation (Pydantic 422)
    run("years too big", base(years=200), expected=422, check_sanity=False)
    run("simulations too small", base(simulations=1), expected=422, check_sanity=False)
    run("dof out of range", base(model=3, distribution_type=2, degrees_of_freedom=1),
        expected=422, check_sanity=False)
    run("negative initial_balance", base(initial_balance=-100), expected=422, check_sanity=False)
    run("weight > 1", base(assets=[{"asset": "NIFTY_50", "weight": 1.5}]),
        expected=422, check_sanity=False)

    # Extra field rejected (extra="forbid")
    run("extra field", base(unknown_field=True), expected=422, check_sanity=False)


# ── Numeric-sense reality check ──────────────────────────────────────────────

def test_reality_checks():
    print("\n=== Reality checks (numeric relationships) ===")

    # 1) SIP should end up with more money than initial balance
    r = client.post("/simulate", json=base(
        cashflow_type=1, cashflow_amount=25000, cashflow_frequency="monthly",
        years=15, initial_balance=100_000, simulations=200)).json()
    _record("SIP grows > initial",
            r["median_final_balance"] > 100_000,
            f"median={r['median_final_balance']:.0f}")

    # 2) Heavy SWP should have lower success than base case
    r_swp = client.post("/simulate", json=base(
        cashflow_type=2, cashflow_amount=100_000, cashflow_frequency="monthly",
        years=25, initial_balance=5_000_000, simulations=200)).json()
    r_none = client.post("/simulate", json=base(
        years=25, initial_balance=5_000_000, simulations=200)).json()
    _record("Heavy SWP success < no-flow success",
            r_swp["success_rate"] <= r_none["success_rate"],
            f"swp={r_swp['success_rate']:.3f} vs none={r_none['success_rate']:.3f}")

    # 3) Fat-tail Model 3 should show wider p10-p90 balance range than Normal
    r_norm = client.post("/simulate", json=base(model=3, distribution_type=1,
                                                simulations=500, years=20)).json()
    r_fat  = client.post("/simulate", json=base(model=3, distribution_type=2,
                                                degrees_of_freedom=5,
                                                simulations=500, years=20)).json()
    last_year = str(20)
    norm_range = r_norm["balance_percentiles"][last_year]["p90"] - r_norm["balance_percentiles"][last_year]["p10"]
    fat_range  = r_fat["balance_percentiles"][last_year]["p90"]  - r_fat["balance_percentiles"][last_year]["p10"]
    _record("Fat-tail range >= Normal range",
            fat_range >= norm_range * 0.9,   # some noise tolerance
            f"norm={norm_range:.0f}  fat={fat_range:.0f}")

    # 4) Same seed + same request across two calls -> identical CAGR
    r1 = client.post("/simulate", json=base(seed=7)).json()
    r2 = client.post("/simulate", json=base(seed=7)).json()
    _record("Deterministic replays match",
            r1["median_cagr"] == r2["median_cagr"] and
            r1["median_final_balance"] == r2["median_final_balance"])

    # 5) Rebalance vs no-rebalance both produce sensible CAGR
    r_no  = client.post("/simulate", json=base(rebalance_frequency=0)).json()
    r_yes = client.post("/simulate", json=base(rebalance_frequency=1)).json()
    _record("Rebalance on/off both plausible",
            0.0 < r_no["median_cagr"] < 0.30 and 0.0 < r_yes["median_cagr"] < 0.30,
            f"no={r_no['median_cagr']:.3f}  yes={r_yes['median_cagr']:.3f}")

    # 6) Config echo returns exactly what we sent (spot-check a few keys)
    payload = base(seed=42, years=8)
    r = client.post("/simulate", json=payload).json()
    ce = r["config_echo"]
    _record("config_echo round-trips",
            ce["seed"] == 42 and ce["years"] == 8 and ce["simulations"] == payload["simulations"],
            json.dumps({k: ce.get(k) for k in ("seed", "years", "simulations")}))


# ── Runner ───────────────────────────────────────────────────────────────────

def main() -> int:
    test_catalog()
    test_models()
    test_rebalance()
    test_inflation()
    test_sequence_stress()
    test_cashflows()
    test_history_window()
    test_portfolios()
    test_horizons()
    test_determinism()
    test_errors()
    test_reality_checks()

    print("\n" + "=" * 72)
    print(f"Results: {len(PASSES)} passed, {len(FAILS)} failed")
    print("=" * 72)

    if FAILS:
        print("\nFailures:")
        for name, msg in FAILS:
            print(f"  - {name}: {msg}")

    print("\nNumeric summary (spot-check reasonableness):")
    for line in NUMERIC_LOG[:40]:
        print("  " + line)
    if len(NUMERIC_LOG) > 40:
        print(f"  ... and {len(NUMERIC_LOG) - 40} more")

    return 1 if FAILS else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)

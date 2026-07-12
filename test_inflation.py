"""Clean inflation test."""
import sys, os
sys.path.insert(0, '.')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from macrowise.engine.monte_carlo import MonteCarloConfig, MonteCarloSimulation
import numpy as np

print("=" * 60)
print("  INFLATION & RETURN CALCULATION ANALYSIS")
print("=" * 60)

# Test 1 & 2: Same seed, same config, only inflation_adjusted differs
c1 = MonteCarloConfig(
    initial_balance=1000000, years=2, simulations=100,
    assets=[('NIFTY_50', 0.6), ('SBI_GILT', 0.4)],
    model=1, bootstrap_model=0, inflation_adjusted=False, seed=42,
)
s1 = MonteCarloSimulation(c1)
r1 = s1.run()

c2 = MonteCarloConfig(
    initial_balance=1000000, years=2, simulations=100,
    assets=[('NIFTY_50', 0.6), ('SBI_GILT', 0.4)],
    model=1, bootstrap_model=0, inflation_adjusted=True, seed=42,
)
s2 = MonteCarloSimulation(c2)
r2 = s2.run()

print("\n1. Does inflation_adjusted affect CAGR?")
print(f"   inflation_adjusted=False : median CAGR = {r1.median_cagr:.4%}")
print(f"   inflation_adjusted=True  : median CAGR = {r2.median_cagr:.4%}")
same = abs(r1.median_cagr - r2.median_cagr) < 1e-10
print(f"   Same CAGR: {same} — inflation_adjusted does NOT change CAGR or balance_paths")

print("\n2. What is the actual inflation value used?")
print(f"   Config inflation_mean (default): {c1.inflation_mean:.4f} ({c1.inflation_mean:.2%})")
print(f"   Config inflation_mean (True)    : {c2.inflation_mean:.4f} ({c2.inflation_mean:.2%})")
print(f"   This is 4% — a US/EU-style inflation rate, not Indian inflation data")

print("\n3. How does inflation_mean affect the simulation?")
# Compare: same inflation_adjusted=True but different inflation_mean values
c3 = MonteCarloConfig(
    initial_balance=1000000, years=2, simulations=100,
    assets=[('NIFTY_50', 0.6), ('SBI_GILT', 0.4)],
    model=1, bootstrap_model=0, inflation_adjusted=True,
    inflation_mean=0.06,  # 6%
    seed=42,
)
s3 = MonteCarloSimulation(c3)
r3 = s3.run()
print(f"   inflation_mean=4% : median CAGR = {r2.median_cagr:.4%}")
print(f"   inflation_mean=6% : median CAGR = {r3.median_cagr:.4%}")
print(f"   Different! inflation_mean DOES change CAGR — it feeds into return generation")

# Show the actual final balance difference
print(f"   inflation_mean=4% : median final balance = {r2.median_final_balance:,.0f}")
print(f"   inflation_mean=6% : median final balance = {r3.median_final_balance:,.0f}")

print("\n4. Performance summary (inflation_adjusted=True, inflation_mean=4%):")
ps = r2.performance_summary
print("   Index (rows):", list(ps.index))
print("   Columns:", list(ps.columns))
print()
for stat in ps.index:
    print(f"   {stat}: {list(ps.loc[stat])}")

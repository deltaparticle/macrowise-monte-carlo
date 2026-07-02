"""
Monte Carlo Simulator — Entry Point
Run via: python main.py
"""
import macrowise  # noqa: F401 — validates imports on startup

if __name__ == "__main__":
    from macrowise import MonteCarloConfig, MonteCarlo, format_inr

    print("=" * 60)
    print("  Macrowise Monte Carlo Simulator")
    print("=" * 60)
    print()
    print("Quick demo: 60/40 Nifty 50 / SBI Gilt, 30 years, 100 sims")
    print()

    config = MonteCarloConfig(
        initial_balance=10_00_000,
        years=30,
        simulations=100,
        assets=[("NIFTY_50", 0.60), ("SBI_GILT", 0.40)],
        model=1,
        bootstrap_model=1,
        seed=42,
        inflation_adjusted=False,
    )
    sim = MonteCarlo(config)
    results = sim.run()

    print(f"Simulations : {results.n_sims}")
    print(f"Years       : {results.n_years}")
    print(f"Median CAGR : {results.median_cagr:.2%}")
    print(f"Success Rate: {results.success_rate:.1%}")
    print(f"Final Balance: INR {results.median_final_balance:,.0f}")
    print()
    print("Full results available via the Python API:")
    print("  from macrowise import MonteCarloConfig, MonteCarlo")

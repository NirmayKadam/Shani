"""
File Overview: Master Experiment Orchestrator for Alpha Generation Research Paper.
Executes the empirical comparison of Crank-Nicolson PDE Mispricing vs Retail Technical Indicators,
generates all academic tables and figures, and exports trade audit logs.
"""

import os
import sys
import logging
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from research.data.collect_historical import HistoricalDataCollector
from research.models.friction_model import IndianOptionsFrictionModel
from research.backtest.engine import BacktestEngine
from research.backtest.strategies import (
    RetailBaselineStrategy,
    PDEMispricingStrategy,
    HybridFilterStrategy,
)
from research.analysis.metrics import (
    generate_comparison_dataframe,
    to_latex_table,
    to_markdown_table,
)
from research.analysis.robustness import RobustnessAnalyzer
from research.analysis.plots import FigureGenerator

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    logger.info("=" * 70)
    logger.info("AlphaStreams Empirical Research Engine — NIFTY 50 Options Backtest")
    logger.info("=" * 70)

    # Setup directories
    base_dir = os.path.abspath(os.path.dirname(__file__))
    data_dir = os.path.join(base_dir, "data", "raw")
    tables_dir = os.path.join(base_dir, "output", "tables")
    figures_dir = os.path.join(base_dir, "output", "figures")
    trade_logs_dir = os.path.join(base_dir, "output", "trade_logs")

    for d in [tables_dir, figures_dir, trade_logs_dir]:
        os.makedirs(d, exist_ok=True)

    # 1. Load Datasets
    ohlcv_path = os.path.join(data_dir, "nifty_daily_ohlcv.parquet")
    options_path = os.path.join(data_dir, "nifty_option_chains.parquet")

    if not os.path.exists(ohlcv_path) or not os.path.exists(options_path):
        logger.info("Dataset not found locally. Triggering data collection pipeline...")
        collector = HistoricalDataCollector(output_dir=data_dir)
        collector.build_and_save_all(days=180)

    ohlcv_df = pd.read_parquet(ohlcv_path)
    options_df = pd.read_parquet(options_path)

    logger.info(f"Loaded {len(ohlcv_df)} daily OHLCV bars and {len(options_df)} option chain strike records.")

    # 2. Run Strategy Backtests
    initial_capital = 100_000.0
    engine = BacktestEngine(initial_capital=initial_capital, lot_size=50)
    dates_list = ohlcv_df["date"].tolist()

    strategies = [
        RetailBaselineStrategy(holding_period=5),
        PDEMispricingStrategy(holding_period=5, buffer_multiplier=1.5),
        HybridFilterStrategy(holding_period=5, buffer_multiplier=1.5),
    ]

    results = []
    for strat in strategies:
        logger.info(f"Executing backtest for strategy: {strat.name}...")
        trades = strat.generate_trades(ohlcv_df, options_df, engine)
        res = engine.calculate_portfolio_metrics(strat.name, trades, dates_list)
        results.append(res)

        # Export individual trade log
        if trades:
            trades_df = pd.DataFrame([t.__dict__ for t in trades])
            trades_df.to_csv(os.path.join(trade_logs_dir, f"{strat.name}_trades.csv"), index=False)

    # 3. Generate Summary Comparison Table
    summary_df = generate_comparison_dataframe(results)
    print("\n" + "=" * 70)
    print("EMPIRICAL STRATEGY PERFORMANCE SUMMARY (Post-Friction)")
    print("=" * 70)
    print(to_markdown_table(summary_df))
    print("=" * 70 + "\n")

    summary_df.to_csv(os.path.join(tables_dir, "strategy_comparison.csv"), index=False)
    with open(os.path.join(tables_dir, "strategy_comparison.tex"), "w", encoding="utf-8") as f:
        f.write(to_latex_table(summary_df, caption="Empirical Performance Comparison of PDE Solvers vs Retail Indicators (NIFTY 50)"))

    # 4. Robustness & Sensitivity Tests
    logger.info("Executing robustness tests and sensitivity sweeps...")
    analyzer = RobustnessAnalyzer(ohlcv_df, options_df, initial_capital=initial_capital)

    stress_df = analyzer.run_friction_stress_test([1.0, 1.5, 2.0, 3.0])
    stress_df.to_csv(os.path.join(tables_dir, "friction_stress_test.csv"), index=False)

    vix_df = analyzer.run_vix_regime_analysis()
    if not vix_df.empty:
        vix_df.to_csv(os.path.join(tables_dir, "vix_regime_analysis.csv"), index=False)
        print("VIX REGIME ANALYSIS:")
        print(to_markdown_table(vix_df) + "\n")

    wf_df = analyzer.run_walk_forward_validation(train_bars=60, test_bars=30)
    if not wf_df.empty:
        wf_df.to_csv(os.path.join(tables_dir, "walk_forward_validation.csv"), index=False)
        print("WALK-FORWARD ROLLING VALIDATION:")
        print(to_markdown_table(wf_df) + "\n")

    # 5. Generate Publication Figures
    logger.info("Generating publication-quality charts (PNG and PDF)...")
    plotter = FigureGenerator(output_dir=figures_dir)
    plotter.plot_equity_curves(results)
    plotter.plot_drawdown_profiles(results)
    plotter.plot_mispricing_distribution(options_df)
    plotter.plot_friction_stress_test(stress_df)

    logger.info(f"[SUCCESS] All research artifacts generated in: {os.path.join(base_dir, 'output')}")


if __name__ == "__main__":
    main()

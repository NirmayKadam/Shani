"""
File Overview: Master 3.5-Year Experiment Orchestrator (Jan 2021 - Jun 2024).
Executes the empirical research comparison across Indian Index Options under the corrected pipeline:
1. Sub-Period Out-of-Sample Tests (Period A, Period B, Period C, Period D, Combined OOS, Full 3.5Y).
2. True Daily Mark-to-Market (MTM) Accounting across all 860 trading sessions.
3. i+1 Execution Lag (Signals at bar i, filled at bar i+1 with liquidity/volume guards).
4. Fixed 50-Unit Position Sizing (eliminating arbitrary 75 -> 50 -> 25 contract distortions).
5. VIX Regime Segmentation using pre-committed Period D quantile bands.
6. Dual Stress Tests: Entry threshold epsilon fixed vs epsilon scaled under 1.0x, 1.5x, 2.0x, 3.0x frictions.
7. Publication Figures (300 DPI PNG & PDF) and Academic LaTeX / Markdown Tables.
"""

import os
import sys
import logging
from datetime import date
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from research.models.nifty_market_rules import get_nifty_lot_size, get_rbi_repo_rate, get_stt_rate, Black76Engine
from research.models.friction_model import IndianOptionsFrictionModel
from research.backtest.engine import BacktestEngine, Trade, BacktestResult
from research.analysis.metrics import to_latex_table, to_markdown_table

logger = logging.getLogger("Master3_5YRunner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class RobustBacktestStrategy:
    """
    Standardized strategy executor supporting:
    - Pure Mispricing vs Hybrid Filter vs Retail Baseline
    - i+1 execution lag
    - Fixed 50-unit sizing
    - Dynamic epsilon with customizable scaling
    """

    def __init__(
        self,
        strategy_type: str = "PURE_PDE",  # 'PURE_PDE', 'HYBRID', 'RETAIL'
        holding_period: int = 5,
        buffer_multiplier: float = 1.5,
        stop_loss_pct: float = 0.35,
        take_profit_pct: float = 0.60,
        fixed_units: int = 50,
        scale_entry_epsilon: bool = False,
        friction_multiplier: float = 1.0,
    ) -> None:
        self.strategy_type = strategy_type
        self.holding_period = holding_period
        self.buffer_multiplier = buffer_multiplier
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.fixed_units = fixed_units
        self.scale_entry_epsilon = scale_entry_epsilon
        self.friction_multiplier = friction_multiplier

    def generate_trades(
        self,
        ohlcv_df: pd.DataFrame,
        options_df: pd.DataFrame,
        engine: BacktestEngine,
    ) -> List[Trade]:
        trades: List[Trade] = []
        trade_id = 1
        active_trade: Optional[Dict[str, Any]] = None
        pending_signal: Optional[Dict[str, Any]] = None
        current_equity = engine.initial_capital

        options_grouped = options_df.groupby("date")
        dates_list = ohlcv_df["date"].tolist()

        # Build friction model with multiplier
        f_mult = self.friction_multiplier if self.scale_entry_epsilon else 1.0
        eff_friction_model = IndianOptionsFrictionModel(default_lot_size=self.fixed_units, multiplier=self.friction_multiplier)
        entry_threshold_model = IndianOptionsFrictionModel(default_lot_size=self.fixed_units, multiplier=f_mult)

        for i, current_date in enumerate(dates_list):
            if current_date not in options_grouped.groups:
                continue

            day_options = options_grouped.get_group(current_date)
            row = ohlcv_df.iloc[i]
            rsi = row.get("rsi")
            macd_hist = row.get("macd_hist")

            # 1. Fill Pending Signal from bar i-1 (i+1 execution lag)
            if active_trade is None and pending_signal is not None:
                target_strike = pending_signal["strike"]
                opt_type = pending_signal["option_type"]
                strike_row = day_options[day_options["strike"] == target_strike]

                if not strike_row.empty:
                    fill_price = (
                        float(strike_row["call_mkt_price"].iloc[0])
                        if opt_type == "call"
                        else float(strike_row["put_mkt_price"].iloc[0])
                    )
                    vol = (
                        float(strike_row["call_contracts"].iloc[0])
                        if opt_type == "call"
                        else float(strike_row["put_contracts"].iloc[0])
                    )

                    # Liquidity guard: price > 5.0 and contracts traded > 0
                    if fill_price > 5.0 and vol > 0:
                        notional = fill_price * self.fixed_units
                        if notional <= current_equity * 0.95:
                            active_trade = {
                                "entry_date": current_date,
                                "entry_bar_idx": i,
                                "option_type": opt_type,
                                "strike": target_strike,
                                "entry_price": fill_price,
                                "quantity": self.fixed_units,
                                "epsilon": pending_signal["epsilon"],
                                "signal": pending_signal["signal"],
                            }
                pending_signal = None

            # 2. Manage Active Trade
            if active_trade is not None:
                bars_held = i - active_trade["entry_bar_idx"]
                target_strike = active_trade["strike"]
                opt_type = active_trade["option_type"]

                strike_row = day_options[day_options["strike"] == target_strike]
                if not strike_row.empty:
                    current_price = (
                        float(strike_row["call_mkt_price"].iloc[0])
                        if opt_type == "call"
                        else float(strike_row["put_mkt_price"].iloc[0])
                    )
                    current_mispricing = (
                        float(strike_row["call_mispricing"].iloc[0])
                        if opt_type == "call"
                        else float(strike_row["put_mispricing"].iloc[0])
                    )
                else:
                    current_price = active_trade["entry_price"]
                    current_mispricing = 0.0

                pnl_per_unit = current_price - active_trade["entry_price"]
                pnl_pct = pnl_per_unit / active_trade["entry_price"] if active_trade["entry_price"] > 0 else 0.0

                exit_reason = None
                if pnl_pct <= -self.stop_loss_pct:
                    exit_reason = "STOP_LOSS"
                elif pnl_pct >= self.take_profit_pct:
                    exit_reason = "TAKE_PROFIT"
                elif bars_held >= 2 and abs(current_mispricing) < (active_trade["epsilon"] / 2.0) and self.strategy_type != "RETAIL":
                    exit_reason = "MEAN_REVERTED"
                elif bars_held >= self.holding_period:
                    exit_reason = "TIME_EXPIRY"

                if exit_reason:
                    qty = active_trade["quantity"]
                    friction_est = eff_friction_model.estimate(
                        premium=active_trade["entry_price"], lot_size=qty
                    )
                    total_friction = friction_est.total_round_trip * qty
                    pnl_gross = pnl_per_unit * qty
                    pnl_net = pnl_gross - total_friction

                    trades.append(
                        Trade(
                            trade_id=trade_id,
                            entry_date=active_trade["entry_date"],
                            exit_date=current_date,
                            symbol="NIFTY",
                            strike=active_trade["strike"],
                            option_type=opt_type,
                            quantity=qty,
                            entry_price=active_trade["entry_price"],
                            exit_price=current_price,
                            entry_signal=active_trade["signal"],
                            exit_signal=exit_reason,
                            pnl_gross=round(pnl_gross, 2),
                            pnl_net=round(pnl_net, 2),
                            friction_paid=round(total_friction, 2),
                            holding_bars=bars_held,
                            is_win=(pnl_net > 0),
                        )
                    )
                    current_equity += pnl_net
                    trade_id += 1
                    active_trade = None

            # 3. Check for New Signal at Bar i
            if active_trade is None and pending_signal is None and i < len(dates_list) - 1:
                spot_price = float(row["close"])

                if self.strategy_type == "RETAIL":
                    # Retail Baseline (ATM RSI + MACD)
                    atm_opts = day_options[day_options["is_atm"] == True]
                    if not atm_opts.empty and rsi is not None and macd_hist is not None:
                        atm_row = atm_opts.iloc[0]
                        c_p = float(atm_row["call_mkt_price"])
                        p_p = float(atm_row["put_mkt_price"])
                        # Bullish setup
                        if ((rsi > 50.0 and macd_hist > 0) or (rsi <= 45.0 and macd_hist > 0)) and c_p > 10.0:
                            pending_signal = {
                                "signal_date": current_date,
                                "option_type": "call",
                                "strike": float(atm_row["strike"]),
                                "epsilon": 0.0,
                                "signal": "RSI_MACD_BULL",
                            }
                        # Bearish setup
                        elif ((rsi < 50.0 and macd_hist < 0) or (rsi >= 55.0 and macd_hist < 0)) and p_p > 10.0:
                            pending_signal = {
                                "signal_date": current_date,
                                "option_type": "put",
                                "strike": float(atm_row["strike"]),
                                "epsilon": 0.0,
                                "signal": "RSI_MACD_BEAR",
                            }
                else:
                    # Model Mispricing (Pure or Hybrid)
                    for _, opt in day_options.iterrows():
                        strike = float(opt["strike"])
                        if abs(strike - spot_price) > 150.0:
                            continue

                        call_price = float(opt["call_mkt_price"])
                        put_price = float(opt["put_mkt_price"])
                        call_mispricing = float(opt["call_mispricing"])
                        put_mispricing = float(opt["put_mispricing"])

                        call_eps = entry_threshold_model.compute_epsilon(
                            premium=call_price, buffer_multiplier=self.buffer_multiplier
                        )
                        put_eps = entry_threshold_model.compute_epsilon(
                            premium=put_price, buffer_multiplier=self.buffer_multiplier
                        )

                        # Hybrid Filter Conditions
                        bull_filter = True
                        bear_filter = True
                        if self.strategy_type == "HYBRID":
                            bull_filter = (macd_hist is not None and macd_hist > 0 and rsi is not None and 35.0 <= rsi <= 70.0)
                            bear_filter = (macd_hist is not None and macd_hist < 0 and rsi is not None and 30.0 <= rsi <= 65.0)

                        if call_mispricing < -call_eps and call_price > 10.0 and bull_filter:
                            pending_signal = {
                                "signal_date": current_date,
                                "option_type": "call",
                                "strike": strike,
                                "epsilon": call_eps,
                                "signal": f"CALL_UNDERVALUED_{call_mispricing:.2f}",
                            }
                            break
                        elif put_mispricing < -put_eps and put_price > 10.0 and bear_filter:
                            pending_signal = {
                                "signal_date": current_date,
                                "option_type": "put",
                                "strike": strike,
                                "epsilon": put_eps,
                                "signal": f"PUT_UNDERVALUED_{put_mispricing:.2f}",
                            }
                            break

        return trades


def run_master_3_5y_experiments():
    logger.info("=" * 75)
    logger.info("ALPHA STREAMS MASTER 3.5-YEAR EXPERIMENT ENGINE (2021 - 2024)")
    logger.info("=" * 75)

    base_dir = os.path.abspath(os.path.dirname(__file__))
    data_dir = os.path.join(base_dir, "data", "raw")
    tables_dir = os.path.join(base_dir, "output", "tables")
    figures_dir = os.path.join(base_dir, "output", "figures")
    os.makedirs(tables_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)

    ohlcv_df = pd.read_parquet(os.path.join(data_dir, "nifty_3_5y_daily_ohlcv.parquet"))
    options_df = pd.read_parquet(os.path.join(data_dir, "nifty_3_5y_option_chains.parquet"))

    # Fetch and merge India VIX
    logger.info("Fetching and merging India VIX for regime segmentation...")
    vix_df = yf.download("^INDIAVIX", start="2021-01-01", end="2024-07-02", progress=False)
    if isinstance(vix_df.columns, pd.MultiIndex):
        vix_df.columns = [c[0].lower() for c in vix_df.columns]
    else:
        vix_df.columns = [c.lower() for c in vix_df.columns]
    vix_df = vix_df.reset_index().rename(columns={"Date": "date", "close": "india_vix"})
    vix_df["date"] = pd.to_datetime(vix_df["date"]).dt.date
    ohlcv_df = pd.merge(ohlcv_df, vix_df[["date", "india_vix"]], on="date", how="left")
    ohlcv_df["india_vix"] = ohlcv_df["india_vix"].ffill().bfill()

    dates_list = ohlcv_df["date"].tolist()
    engine = BacktestEngine(initial_capital=100_000.0, lot_size=50)

    # Sub-Period Date Windows
    sub_periods = {
        "Period A (2021 OOS)": (date(2021, 1, 1), date(2021, 12, 31)),
        "Period B (2022 OOS)": (date(2022, 1, 1), date(2022, 12, 31)),
        "Period C (Jan-Sep 2023 OOS)": (date(2023, 1, 1), date(2023, 9, 30)),
        "Combined OOS (A+B+C)": (date(2021, 1, 1), date(2023, 9, 30)),
        "Period D (Oct 2023-Jun 2024 Dev)": (date(2023, 10, 1), date(2024, 6, 28)),
        "Full Sample (3.5 Years)": (date(2021, 1, 1), date(2024, 6, 28)),
    }

    # 1. RUN STRATEGIES ON FULL 3.5-YEAR PANEL
    logger.info("Executing strategies across full 3.5-year panel...")
    strat_pure = RobustBacktestStrategy(strategy_type="PURE_PDE", holding_period=5, fixed_units=50)
    strat_hybrid = RobustBacktestStrategy(strategy_type="HYBRID", holding_period=5, fixed_units=50)
    strat_retail = RobustBacktestStrategy(strategy_type="RETAIL", holding_period=5, fixed_units=50)

    trades_pure_all = strat_pure.generate_trades(ohlcv_df, options_df, engine)
    trades_hybrid_all = strat_hybrid.generate_trades(ohlcv_df, options_df, engine)
    trades_retail_all = strat_retail.generate_trades(ohlcv_df, options_df, engine)

    logger.info(f"Full 3.5Y Trades Generated: Pure Mispricing={len(trades_pure_all)}, Hybrid={len(trades_hybrid_all)}, Retail={len(trades_retail_all)}")

    # 2. SUB-PERIOD OOS ANALYSIS
    subperiod_records = []
    equity_curves = {}

    for period_name, (start_dt, end_dt) in sub_periods.items():
        period_dates = [d for d in dates_list if start_dt <= d <= end_dt]
        period_options = options_df[(options_df["date"] >= start_dt) & (options_df["date"] <= end_dt)]

        p_trades_pure = [t for t in trades_pure_all if start_dt <= t.entry_date <= end_dt]
        p_trades_hybrid = [t for t in trades_hybrid_all if start_dt <= t.entry_date <= end_dt]
        p_trades_retail = [t for t in trades_retail_all if start_dt <= t.entry_date <= end_dt]

        res_pure = engine.calculate_portfolio_metrics(f"Pure_PDE_{period_name}", p_trades_pure, period_dates, options_df=period_options)
        res_hybrid = engine.calculate_portfolio_metrics(f"Hybrid_{period_name}", p_trades_hybrid, period_dates, options_df=period_options)
        res_retail = engine.calculate_portfolio_metrics(f"Retail_{period_name}", p_trades_retail, period_dates, options_df=period_options)

        if period_name == "Full Sample (3.5 Years)":
            equity_curves["Pure_PDE"] = res_pure.equity_curve
            equity_curves["Hybrid"] = res_hybrid.equity_curve
            equity_curves["Retail"] = res_retail.equity_curve

        for sname, res in [("Pure Mispricing", res_pure), ("Hybrid Filter", res_hybrid), ("Retail Baseline", res_retail)]:
            subperiod_records.append(
                {
                    "Sub_Period": period_name,
                    "Strategy": sname,
                    "Return_Pct": res.total_return_pct,
                    "Sharpe": res.sharpe_ratio,
                    "Sortino": res.sortino_ratio,
                    "Max_DD_Pct": res.max_drawdown_pct,
                    "Win_Rate_Pct": res.win_rate,
                    "Trades": len(res.trades),
                    "Final_Capital": res.final_capital,
                }
            )

    subperiod_df = pd.DataFrame(subperiod_records)
    subperiod_df.to_csv(os.path.join(tables_dir, "subperiod_performance_3_5y.csv"), index=False)
    with open(os.path.join(tables_dir, "subperiod_performance_3_5y.tex"), "w", encoding="utf-8") as f:
        f.write(to_latex_table(subperiod_df, caption="Sub-Period Out-of-Sample Performance Across 3.5 Years (2021-2024)"))

    print("\n" + "=" * 75)
    print("SUB-PERIOD PERFORMANCE ACROSS 3.5 YEARS (2021 - 2024):")
    print("=" * 75)
    print(to_markdown_table(subperiod_df))
    print("=" * 75 + "\n")

    # 3. VIX REGIME ANALYSIS (Pre-fixed Period D bands: <12.6, 12.6-14.5, >14.5)
    logger.info("Executing India VIX regime segmentation...")
    vix_dict = dict(zip(ohlcv_df["date"], ohlcv_df["india_vix"]))
    vix_bands = {
        "Low VIX (< 12.6)": lambda v: v < 12.6,
        "Normal VIX (12.6 - 14.5)": lambda v: 12.6 <= v <= 14.5,
        "High VIX (> 14.5)": lambda v: v > 14.5,
    }

    vix_records = []
    for regime_name, condition in vix_bands.items():
        regime_dates = [d for d in dates_list if condition(vix_dict.get(d, 13.0))]
        regime_options = options_df[options_df["date"].isin(regime_dates)]

        r_trades_pure = [t for t in trades_pure_all if condition(vix_dict.get(t.entry_date, 13.0))]
        r_trades_retail = [t for t in trades_retail_all if condition(vix_dict.get(t.entry_date, 13.0))]

        res_pure = engine.calculate_portfolio_metrics(f"Pure_PDE_{regime_name}", r_trades_pure, regime_dates, options_df=regime_options)
        res_retail = engine.calculate_portfolio_metrics(f"Retail_{regime_name}", r_trades_retail, regime_dates, options_df=regime_options)

        vix_records.append(
            {
                "VIX_Regime": regime_name,
                "Strategy": "Pure Mispricing",
                "Return_Pct": res_pure.total_return_pct,
                "Sharpe": res_pure.sharpe_ratio,
                "Sortino": res_pure.sortino_ratio,
                "Win_Rate_Pct": res_pure.win_rate,
                "Trades": len(res_pure.trades),
            }
        )
        vix_records.append(
            {
                "VIX_Regime": regime_name,
                "Strategy": "Retail Baseline",
                "Return_Pct": res_retail.total_return_pct,
                "Sharpe": res_retail.sharpe_ratio,
                "Sortino": res_retail.sortino_ratio,
                "Win_Rate_Pct": res_retail.win_rate,
                "Trades": len(res_retail.trades),
            }
        )

    vix_df_summary = pd.DataFrame(vix_records)
    vix_df_summary.to_csv(os.path.join(tables_dir, "vix_regime_analysis_3_5y.csv"), index=False)
    print("VIX REGIME ANALYSIS (3.5 YEARS):")
    print(to_markdown_table(vix_df_summary) + "\n")

    # 4. DUAL FRICTION STRESS TESTS (Epsilon Fixed vs Epsilon Scaled)
    logger.info("Executing dual friction stress tests...")
    multipliers = [1.0, 1.5, 2.0, 3.0]
    stress_records = []

    for mult in multipliers:
        # Form 1: Realized Friction Scaled, Epsilon Fixed
        s_strat_fixed = RobustBacktestStrategy(strategy_type="PURE_PDE", fixed_units=50, friction_multiplier=mult, scale_entry_epsilon=False)
        t_fixed = s_strat_fixed.generate_trades(ohlcv_df, options_df, engine)
        r_fixed = engine.calculate_portfolio_metrics(f"Fixed_Eps_{mult}x", t_fixed, dates_list, options_df=options_df)

        # Form 2: Realized Friction Scaled AND Epsilon Scaled
        s_strat_scaled = RobustBacktestStrategy(strategy_type="PURE_PDE", fixed_units=50, friction_multiplier=mult, scale_entry_epsilon=True)
        t_scaled = s_strat_scaled.generate_trades(ohlcv_df, options_df, engine)
        r_scaled = engine.calculate_portfolio_metrics(f"Scaled_Eps_{mult}x", t_scaled, dates_list, options_df=options_df)

        stress_records.append(
            {
                "Multiplier": f"{mult:.1f}x",
                "Protocol": "Epsilon Fixed (Threshold Constant)",
                "Return_Pct": r_fixed.total_return_pct,
                "Sharpe": r_fixed.sharpe_ratio,
                "Max_DD_Pct": r_fixed.max_drawdown_pct,
                "Trades": len(t_fixed),
            }
        )
        stress_records.append(
            {
                "Multiplier": f"{mult:.1f}x",
                "Protocol": "Epsilon Scaled (Threshold Scales with Friction)",
                "Return_Pct": r_scaled.total_return_pct,
                "Sharpe": r_scaled.sharpe_ratio,
                "Max_DD_Pct": r_scaled.max_drawdown_pct,
                "Trades": len(t_scaled),
            }
        )

    stress_df = pd.DataFrame(stress_records)
    stress_df.to_csv(os.path.join(tables_dir, "friction_stress_test_3_5y.csv"), index=False)
    print("DUAL FRICTION STRESS TESTS (3.5 YEARS):")
    print(to_markdown_table(stress_df) + "\n")

    # 5. GENERATE PUBLICATION FIGURES (300 DPI)
    logger.info("Generating publication-quality charts (PNG and PDF)...")
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    # Figure 1: 3.5-Year Equity Curves
    if "Pure_PDE" in equity_curves and "Retail" in equity_curves:
        fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
        df_pure = equity_curves["Pure_PDE"]
        df_retail = equity_curves["Retail"]
        ax.plot(pd.to_datetime(df_pure["date"]), df_pure["equity"], label="Pure Mispricing (i+1 Lag, MTM)", color="#10B981", linewidth=2.0)
        ax.plot(pd.to_datetime(df_retail["date"]), df_retail["equity"], label="Retail Baseline (RSI+MACD)", color="#EF4444", linewidth=1.5, linestyle="--")
        ax.set_title("3.5-Year Cumulative Equity Growth: Institutional Mispricing vs Retail Heuristics", fontsize=12, fontweight="bold")
        ax.set_ylabel("Portfolio Value (INR)")
        ax.set_xlabel("Trading Date")
        ax.legend(loc="upper left")
        plt.tight_layout()
        fig.savefig(os.path.join(figures_dir, "fig1_equity_curves_3_5y.png"))
        fig.savefig(os.path.join(figures_dir, "fig1_equity_curves_3_5y.pdf"))
        plt.close(fig)

    # Figure 2: Sub-Period Performance Comparison Bar Chart
    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
    p_names = ["Period A\n(2021)", "Period B\n(2022)", "Period C\n(Jan-Sep 2023)", "Period D\n(Dev Sample)", "Full 3.5Y\nSample"]
    p_keys = ["Period A (2021 OOS)", "Period B (2022 OOS)", "Period C (Jan-Sep 2023 OOS)", "Period D (Oct 2023-Jun 2024 Dev)", "Full Sample (3.5 Years)"]
    pure_rets = [subperiod_df[(subperiod_df["Sub_Period"] == k) & (subperiod_df["Strategy"] == "Pure Mispricing")]["Return_Pct"].iloc[0] for k in p_keys]
    retail_rets = [subperiod_df[(subperiod_df["Sub_Period"] == k) & (subperiod_df["Strategy"] == "Retail Baseline")]["Return_Pct"].iloc[0] for k in p_keys]
    x = np.arange(len(p_names))
    width = 0.35
    ax.bar(x - width/2, pure_rets, width, label="Pure Mispricing Strategy", color="#10B981")
    ax.bar(x + width/2, retail_rets, width, label="Retail Baseline Strategy", color="#EF4444")
    ax.set_xticks(x)
    ax.set_xticklabels(p_names)
    ax.set_ylabel("Net Total Return (%)")
    ax.set_title("Sub-Period Out-of-Sample Performance Comparison (2021 - 2024)", fontsize=12, fontweight="bold")
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax.legend()
    plt.tight_layout()
    fig.savefig(os.path.join(figures_dir, "fig2_subperiod_comparison_3_5y.png"))
    fig.savefig(os.path.join(figures_dir, "fig2_subperiod_comparison_3_5y.pdf"))
    plt.close(fig)

    logger.info(f"[SUCCESS] All 3.5-year research artifacts saved in: {tables_dir} and {figures_dir}")


if __name__ == "__main__":
    run_master_3_5y_experiments()

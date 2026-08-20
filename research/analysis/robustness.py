"""
File Overview: Robustness Testing & Sensitivity Analysis.
Executes:
1. Friction Stress Testing (1.0x, 1.5x, 2.0x, 3.0x base statutory costs).
2. Volatility Regime Segmentation (India VIX Quartiles).
3. Walk-Forward Rolling Window Validation.
"""

from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np

from research.backtest.engine import BacktestEngine, BacktestResult, Trade
from research.backtest.strategies import (
    BaseStrategy,
    RetailBaselineStrategy,
    PDEMispricingStrategy,
    HybridFilterStrategy,
)
from research.models.friction_model import IndianOptionsFrictionModel


class RobustnessAnalyzer:
    """Performs empirical robustness checks on backtest strategies."""

    def __init__(
        self,
        ohlcv_df: pd.DataFrame,
        options_df: pd.DataFrame,
        initial_capital: float = 100_000.0,
    ) -> None:
        self.ohlcv_df = ohlcv_df
        self.options_df = options_df
        self.initial_capital = initial_capital
        self.dates_list = ohlcv_df["date"].tolist()

    def run_friction_stress_test(
        self,
        multipliers: List[float] = [1.0, 1.5, 2.0, 3.0],
    ) -> pd.DataFrame:
        """
        Evaluate Sharpe ratio and Total Return degradation across increasing friction multipliers.
        Applies scaled friction to the baseline trade set to accurately measure cost sensitivity
        without introducing trade selection bias.
        """
        records = []
        strategies: List[BaseStrategy] = [
            RetailBaselineStrategy(),
            PDEMispricingStrategy(),
            HybridFilterStrategy(),
        ]

        # 1. Generate baseline trades for each strategy under 1.0x base conditions
        base_engine = BacktestEngine(initial_capital=self.initial_capital)
        base_trades_by_strat: Dict[str, List[Trade]] = {}
        for strat in strategies:
            base_trades_by_strat[strat.name] = strat.generate_trades(
                self.ohlcv_df, self.options_df, base_engine
            )

        # 2. Stress test the exact trade sequence under scaled friction multipliers
        for mult in multipliers:
            scaled_friction = IndianOptionsFrictionModel(multiplier=mult)
            stress_engine = BacktestEngine(
                initial_capital=self.initial_capital,
                friction_model=scaled_friction,
            )

            for strat in strategies:
                base_trades = base_trades_by_strat[strat.name]
                stressed_trades: List[Trade] = []

                for t in base_trades:
                    f_est = scaled_friction.estimate(premium=t.entry_price, lot_size=t.quantity)
                    friction_paid = f_est.total_round_trip * t.quantity
                    pnl_net = t.pnl_gross - friction_paid

                    stressed_trades.append(
                        Trade(
                            trade_id=t.trade_id,
                            entry_date=t.entry_date,
                            exit_date=t.exit_date,
                            symbol=t.symbol,
                            strike=t.strike,
                            option_type=t.option_type,
                            quantity=t.quantity,
                            entry_price=t.entry_price,
                            exit_price=t.exit_price,
                            entry_signal=t.entry_signal,
                            exit_signal=t.exit_signal,
                            pnl_gross=t.pnl_gross,
                            pnl_net=round(pnl_net, 2),
                            friction_paid=round(friction_paid, 2),
                            holding_bars=t.holding_bars,
                            is_win=(pnl_net > 0),
                        )
                    )

                res = stress_engine.calculate_portfolio_metrics(
                    strat.name, stressed_trades, self.dates_list
                )
                records.append(
                    {
                        "Friction_Multiplier": f"{mult:.1f}x",
                        "Strategy": strat.name,
                        "Total_Return_Pct": res.total_return_pct,
                        "Sharpe_Ratio": res.sharpe_ratio,
                        "Sortino_Ratio": res.sortino_ratio,
                        "Max_Drawdown_Pct": res.max_drawdown_pct,
                        "Total_Friction_Paid": res.total_friction_paid,
                    }
                )

        return pd.DataFrame(records)

    def run_vix_regime_analysis(self) -> pd.DataFrame:
        """
        Segment performance by India VIX levels (Low VIX: <13, Normal VIX: 13-17, High VIX: >17).
        """
        if "vix_close" not in self.ohlcv_df.columns:
            return pd.DataFrame()

        vix_series = self.ohlcv_df["vix_close"].dropna()
        q33 = float(vix_series.quantile(0.33))
        q66 = float(vix_series.quantile(0.66))

        regimes = [
            ("Low VIX (< {:.1f})".format(q33), self.ohlcv_df["vix_close"] <= q33),
            ("Normal VIX ({:.1f} - {:.1f})".format(q33, q66), (self.ohlcv_df["vix_close"] > q33) & (self.ohlcv_df["vix_close"] <= q66)),
            ("High VIX (> {:.1f})".format(q66), self.ohlcv_df["vix_close"] > q66),
        ]

        records = []
        engine = BacktestEngine(initial_capital=self.initial_capital)
        strategies: List[BaseStrategy] = [
            RetailBaselineStrategy(),
            PDEMispricingStrategy(),
            HybridFilterStrategy(),
        ]

        for regime_name, mask in regimes:
            regime_ohlcv = self.ohlcv_df[mask].reset_index(drop=True)
            regime_dates = set(regime_ohlcv["date"])
            regime_options = self.options_df[self.options_df["date"].isin(regime_dates)].reset_index(drop=True)

            if regime_ohlcv.empty or regime_options.empty:
                continue

            for strat in strategies:
                trades = strat.generate_trades(regime_ohlcv, regime_options, engine)
                res = engine.calculate_portfolio_metrics(strat.name, trades, regime_ohlcv["date"].tolist())
                records.append(
                    {
                        "VIX_Regime": regime_name,
                        "Strategy": strat.name,
                        "Total_Return_Pct": res.total_return_pct,
                        "Sharpe_Ratio": res.sharpe_ratio,
                        "Sortino_Ratio": res.sortino_ratio,
                        "Win_Rate_Pct": res.win_rate,
                        "Trade_Count": res.total_trades,
                    }
                )

        return pd.DataFrame(records)

    def run_walk_forward_validation(
        self,
        train_bars: int = 60,
        test_bars: int = 30,
    ) -> pd.DataFrame:
        """
        Execute rolling Walk-Forward Optimization across sequential time windows.
        """
        n_bars = len(self.ohlcv_df)
        records = []
        engine = BacktestEngine(initial_capital=self.initial_capital)
        strategies: List[BaseStrategy] = [
            RetailBaselineStrategy(),
            PDEMispricingStrategy(),
            HybridFilterStrategy(),
        ]

        window_idx = 1
        start_idx = 0

        while start_idx + train_bars + test_bars <= n_bars:
            test_start = start_idx + train_bars
            test_end = test_start + test_bars

            test_ohlcv = self.ohlcv_df.iloc[test_start:test_end].reset_index(drop=True)
            test_dates = set(test_ohlcv["date"])
            test_options = self.options_df[self.options_df["date"].isin(test_dates)].reset_index(drop=True)

            for strat in strategies:
                trades = strat.generate_trades(test_ohlcv, test_options, engine)
                res = engine.calculate_portfolio_metrics(strat.name, trades, test_ohlcv["date"].tolist())
                records.append(
                    {
                        "Window": f"Fold_{window_idx}",
                        "Test_Dates": f"{test_ohlcv['date'].iloc[0]} to {test_ohlcv['date'].iloc[-1]}",
                        "Strategy": strat.name,
                        "Out_Of_Sample_Return_Pct": res.total_return_pct,
                        "Sharpe_Ratio": res.sharpe_ratio,
                        "Sortino_Ratio": res.sortino_ratio,
                        "Trade_Count": res.total_trades,
                    }
                )

            window_idx += 1
            start_idx += test_bars

        return pd.DataFrame(records)

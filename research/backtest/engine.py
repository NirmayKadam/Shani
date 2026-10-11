"""
File Overview: Quantitative Backtesting Engine for Indian Index Derivatives.
Provides deterministic simulation with full transaction friction modeling, position sizing,
and risk-adjusted portfolio analytics (Sharpe, Sortino, Drawdown, Profit Factor).
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd

from research.models.friction_model import IndianOptionsFrictionModel


@dataclass
class Trade:
    """Individual trade execution record."""
    trade_id: int
    entry_date: date
    exit_date: date
    symbol: str
    strike: float
    option_type: str        # 'call' or 'put'
    quantity: int           # Number of units (e.g. 50 for 1 NIFTY lot)
    entry_price: float      # Premium paid per unit at entry
    exit_price: float       # Premium received per unit at exit
    entry_signal: str       # Reason for entry (e.g. 'RSI_OVERSOLD', 'PDE_UNDERVALUED')
    exit_signal: str        # Reason for exit (e.g. 'TARGET', 'STOP_LOSS', 'EXPIRED')
    pnl_gross: float        # Gross profit/loss in Rupees
    pnl_net: float          # Net profit/loss in Rupees after all frictions
    friction_paid: float    # Total statutory frictions & fees paid
    holding_bars: int       # Number of trading sessions held
    is_win: bool            # Net PnL > 0


@dataclass
class BacktestResult:
    """Aggregated quantitative performance summary."""
    strategy_name: str
    initial_capital: float
    final_capital: float
    total_return_pct: float
    trades: List[Trade] = field(default_factory=list)
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    daily_returns: pd.Series = field(default_factory=pd.Series)
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration: int = 0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    total_trades: int = 0
    total_friction_paid: float = 0.0


class BacktestEngine:
    """
    Deterministic derivatives backtesting engine.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        lot_size: int = 50,
        risk_per_trade_pct: float = 0.05,
        friction_model: Optional[IndianOptionsFrictionModel] = None,
        risk_free_rate: float = 0.065,
    ) -> None:
        self.initial_capital = float(initial_capital)
        self.lot_size = int(lot_size)
        self.risk_per_trade_pct = float(risk_per_trade_pct)
        self.friction_model = friction_model or IndianOptionsFrictionModel(default_lot_size=self.lot_size)
        self.risk_free_rate = float(risk_free_rate)

    def calculate_portfolio_metrics(
        self,
        strategy_name: str,
        trades: List[Trade],
        dates: List[date],
        options_df: Optional[pd.DataFrame] = None,
    ) -> BacktestResult:
        """
        Calculates all portfolio-level and risk-adjusted metrics.
        If options_df is provided, computes true daily Mark-to-Market (MTM) valuation.
        """
        if not trades:
            empty_curve = pd.DataFrame({"date": dates, "equity": [self.initial_capital] * len(dates)})
            return BacktestResult(
                strategy_name=strategy_name,
                initial_capital=self.initial_capital,
                final_capital=self.initial_capital,
                total_return_pct=0.0,
                trades=[],
                equity_curve=empty_curve,
                daily_returns=pd.Series([0.0] * len(dates)),
            )

        # Build options daily price lookup: (date, strike, option_type) -> mkt_price
        options_lookup: Dict[Any, float] = {}
        if options_df is not None:
            for _, r in options_df.iterrows():
                d = r["date"]
                stk = float(r["strike"])
                options_lookup[(d, stk, "call")] = float(r["call_mkt_price"])
                options_lookup[(d, stk, "put")] = float(r["put_mkt_price"])

        if options_lookup:
            # TRUE DAILY MARK-TO-MARKET (MTM) ACCOUNTING
            cash = self.initial_capital
            active_positions: Dict[int, Trade] = {}
            trade_entry_map: Dict[date, List[Trade]] = {}
            trade_exit_map: Dict[date, List[Trade]] = {}

            for t in trades:
                trade_entry_map.setdefault(t.entry_date, []).append(t)
                trade_exit_map.setdefault(t.exit_date, []).append(t)

            daily_records = []
            for d in dates:
                # 1. Process exits on date d
                if d in trade_exit_map:
                    for t in trade_exit_map[d]:
                        if t.trade_id in active_positions:
                            exit_friction = self.friction_model.estimate(t.exit_price, t.quantity).total_round_trip * 0.5 * t.quantity
                            cash += (t.exit_price * t.quantity) - exit_friction
                            del active_positions[t.trade_id]

                # 2. Process entries on date d
                if d in trade_entry_map:
                    for t in trade_entry_map[d]:
                        entry_friction = self.friction_model.estimate(t.entry_price, t.quantity).total_round_trip * 0.5 * t.quantity
                        cost = (t.entry_price * t.quantity) + entry_friction
                        cash -= cost
                        active_positions[t.trade_id] = t

                # 3. Mark active positions to market on date d
                mtm_portfolio_value = 0.0
                for tid, t in active_positions.items():
                    curr_price = options_lookup.get((d, t.strike, t.option_type), t.entry_price)
                    mtm_portfolio_value += curr_price * t.quantity

                total_equity = cash + mtm_portfolio_value
                daily_records.append({"date": d, "cash": cash, "mtm_positions": mtm_portfolio_value, "equity": total_equity})

            equity_df = pd.DataFrame(daily_records)
            equity_df["returns"] = equity_df["equity"].pct_change().fillna(0.0)
        else:
            # Day-by-day cash exit fallback
            daily_pnl: Dict[date, float] = {d: 0.0 for d in dates}
            for t in trades:
                if t.exit_date in daily_pnl:
                    daily_pnl[t.exit_date] += t.pnl_net

            equity = self.initial_capital
            equity_records = []
            for d in dates:
                equity += daily_pnl[d]
                equity_records.append({"date": d, "equity": equity, "daily_pnl": daily_pnl[d]})

            equity_df = pd.DataFrame(equity_records)
            equity_df["returns"] = equity_df["equity"].pct_change().fillna(0.0)

        # Basic Stats
        total_pnl = sum(t.pnl_net for t in trades)
        final_capital = self.initial_capital + total_pnl
        total_return_pct = (total_pnl / self.initial_capital) * 100.0

        wins = [t.pnl_net for t in trades if t.pnl_net > 0]
        losses = [abs(t.pnl_net) for t in trades if t.pnl_net < 0]

        win_rate = (len(wins) / len(trades)) * 100.0 if trades else 0.0
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        profit_factor = (sum(wins) / sum(losses)) if losses and sum(losses) > 0 else (99.0 if wins else 0.0)

        total_friction = sum(t.friction_paid for t in trades)

        # Sharpe & Sortino Ratios (Annualized)
        daily_rets = equity_df["returns"].values
        daily_rf = (1.0 + self.risk_free_rate) ** (1.0 / 252.0) - 1.0
        excess_returns = daily_rets - daily_rf

        std_dev = float(np.std(daily_rets, ddof=1)) if len(daily_rets) > 1 else 0.0
        if std_dev > 1e-6:
            sharpe_ratio = float((np.mean(excess_returns) / std_dev) * np.sqrt(252))
        else:
            sharpe_ratio = 0.0

        # Downside deviation for Sortino
        downside_rets = daily_rets[daily_rets < daily_rf]
        if len(downside_rets) > 1:
            downside_std = float(np.std(downside_rets, ddof=1))
            sortino_ratio = float((np.mean(excess_returns) / downside_std) * np.sqrt(252)) if downside_std > 1e-6 else 0.0
        else:
            sortino_ratio = sharpe_ratio

        # Maximum Drawdown (MDD)
        equity_series = equity_df["equity"].values
        running_max = np.maximum.accumulate(equity_series)
        drawdowns = (running_max - equity_series) / np.maximum(running_max, 1.0)
        max_drawdown_pct = float(np.max(drawdowns)) * 100.0 if len(drawdowns) > 0 else 0.0

        return BacktestResult(
            strategy_name=strategy_name,
            initial_capital=self.initial_capital,
            final_capital=float(round(final_capital, 2)),
            total_return_pct=float(round(total_return_pct, 2)),
            trades=trades,
            equity_curve=equity_df,
            daily_returns=equity_df["returns"],
            sharpe_ratio=float(round(sharpe_ratio, 4)),
            sortino_ratio=float(round(sortino_ratio, 4)),
            max_drawdown_pct=float(round(max_drawdown_pct, 2)),
            profit_factor=float(round(profit_factor, 4)),
            win_rate=float(round(win_rate, 2)),
            avg_win=float(round(avg_win, 2)),
            avg_loss=float(round(avg_loss, 2)),
            total_trades=len(trades),
            total_friction_paid=float(round(total_friction, 2)),
        )

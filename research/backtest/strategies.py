"""
File Overview: Strategy Implementations for Empirical Comparative Backtest.
1. RetailBaselineStrategy: Momentum and reversal heuristic standard (RSI + MACD).
2. PDEMispricingStrategy: Pure Crank-Nicolson PDE statistical arbitrage with dynamic epsilon.
3. HybridFilterStrategy: Composite framework augmenting PDE valuation with momentum filters.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import date
import pandas as pd

from research.backtest.engine import Trade, BacktestEngine, BacktestResult
from research.models.friction_model import IndianOptionsFrictionModel


class BaseStrategy(ABC):
    """Abstract base class for quantitative options backtesting strategies."""

    def __init__(
        self,
        name: str,
        holding_period: int = 5,
        stop_loss_pct: float = 0.35,  # 35% option premium stop loss
        take_profit_pct: float = 0.60, # 60% option premium take profit
    ) -> None:
        self.name = name
        self.holding_period = holding_period
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

    @abstractmethod
    def generate_trades(
        self,
        ohlcv_df: pd.DataFrame,
        options_df: pd.DataFrame,
        engine: BacktestEngine,
    ) -> List[Trade]:
        """Generate simulated trades over historical panel dataset."""
        pass


class RetailBaselineStrategy(BaseStrategy):
    """
    Standard retail strategy executing on momentum and overbought/oversold oscillator signals.
    """

    def __init__(self, holding_period: int = 5) -> None:
        super().__init__(name="Retail_Baseline_RSI_MACD", holding_period=holding_period)

    def generate_trades(
        self,
        ohlcv_df: pd.DataFrame,
        options_df: pd.DataFrame,
        engine: BacktestEngine,
    ) -> List[Trade]:
        trades: List[Trade] = []
        trade_id = 1
        active_trade: Optional[Dict[str, Any]] = None
        # BUG FIX #3: Track current equity to enforce position sizing.
        current_equity = engine.initial_capital

        # Build fast lookup map for option pricing: (date, is_atm, option_type) -> price
        # ATM options map: date -> row
        atm_options = options_df[options_df["is_atm"] == True].set_index("date")

        for i, row in ohlcv_df.iterrows():
            current_date = row["date"]
            rsi = row.get("rsi")
            macd_hist = row.get("macd_hist")

            if current_date not in atm_options.index:
                continue

            atm_row = atm_options.loc[current_date]
            if isinstance(atm_row, pd.DataFrame):
                atm_row = atm_row.iloc[0]

            strike = float(atm_row["strike"])
            call_price = float(atm_row["call_mkt_price"])
            put_price = float(atm_row["put_mkt_price"])

            # 1. Manage Active Trade
            if active_trade is not None:
                bars_held = i - active_trade["entry_bar_idx"]
                opt_type = active_trade["option_type"]
                current_price = call_price if opt_type == "call" else put_price

                exit_reason = None
                pnl_per_unit = current_price - active_trade["entry_price"]
                pnl_pct = pnl_per_unit / active_trade["entry_price"] if active_trade["entry_price"] > 0 else 0.0

                if pnl_pct <= -self.stop_loss_pct:
                    exit_reason = "STOP_LOSS"
                elif pnl_pct >= self.take_profit_pct:
                    exit_reason = "TAKE_PROFIT"
                elif bars_held >= self.holding_period:
                    exit_reason = "TIME_EXPIRY"

                if exit_reason:
                    qty = active_trade["quantity"]
                    friction_est = engine.friction_model.estimate(
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
                    current_equity += pnl_net  # Update running equity
                    trade_id += 1
                    active_trade = None

            # 2. Check Entry Signals (if no active trade)
            if active_trade is None and rsi is not None and macd_hist is not None:
                # BUG FIX #3: Capital check — skip entry if notional exceeds current equity
                max_notional = current_equity * 0.95  # Max 95% of equity per trade
                # Bullish setup: Momentum expansion (RSI > 50 & MACD > 0) or Oversold Pullback (RSI < 45 & MACD > 0)
                if ((rsi > 50.0 and macd_hist > 0) or (rsi <= 45.0 and macd_hist > 0)) and call_price > 10.0:
                    notional = call_price * engine.lot_size
                    if notional <= max_notional:
                        active_trade = {
                            "entry_date": current_date,
                            "entry_bar_idx": i,
                            "option_type": "call",
                            "strike": strike,
                            "entry_price": call_price,
                            "quantity": engine.lot_size,
                            "signal": "RSI_MOMENTUM_MACD_BULL",
                        }
                # Bearish setup: Momentum contraction (RSI < 50 & MACD < 0) or Overbought Reversal (RSI > 55 & MACD < 0)
                elif ((rsi < 50.0 and macd_hist < 0) or (rsi >= 55.0 and macd_hist < 0)) and put_price > 10.0:
                    notional = put_price * engine.lot_size
                    if notional <= max_notional:
                        active_trade = {
                            "entry_date": current_date,
                            "entry_bar_idx": i,
                            "option_type": "put",
                            "strike": strike,
                            "entry_price": put_price,
                            "quantity": engine.lot_size,
                            "signal": "RSI_MOMENTUM_MACD_BEAR",
                        }

        return trades


class PDEMispricingStrategy(BaseStrategy):
    """
    Challenger A: Executes strictly when Crank-Nicolson PDE solver identifies significant
    undervaluation exceeding dynamic friction threshold (C_mkt < C_PDE - epsilon_t).
    """

    def __init__(self, holding_period: int = 5, buffer_multiplier: float = 1.5) -> None:
        super().__init__(name="Challenger_A_Pure_PDE", holding_period=holding_period)
        self.buffer_multiplier = buffer_multiplier

    def generate_trades(
        self,
        ohlcv_df: pd.DataFrame,
        options_df: pd.DataFrame,
        engine: BacktestEngine,
    ) -> List[Trade]:
        trades: List[Trade] = []
        trade_id = 1
        active_trade: Optional[Dict[str, Any]] = None
        current_equity = engine.initial_capital

        options_grouped = options_df.groupby("date")
        dates_list = ohlcv_df["date"].tolist()

        for i, current_date in enumerate(dates_list):
            if current_date not in options_grouped.groups:
                continue

            day_options = options_grouped.get_group(current_date)

            # 1. Manage Active Trade
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
                elif bars_held >= 2 and abs(current_mispricing) < (active_trade["epsilon"] / 2.0):
                    # BUG FIX #2: Require minimum 2-bar hold before allowing mean-reversion exit.
                    # Without this, the daily surface recalibration immediately shows "no mispricing"
                    # on the next bar, causing 0-PnL ghost trades that only bleed friction.
                    exit_reason = "MEAN_REVERTED"
                elif bars_held >= self.holding_period:
                    exit_reason = "TIME_EXPIRY"

                if exit_reason:
                    qty = active_trade["quantity"]
                    friction_est = engine.friction_model.estimate(
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

            # 2. Check Mispricing Signals across available strikes
            if active_trade is None:
                # BUG FIX #4: Restrict to near-ATM strikes only (ATM +/- 2 steps).
                # Deep ITM/OTM far-expiry options show large phantom mispricings
                # due to poor surface fit at the wings, but are illiquid and untradeable.
                spot_price = float(ohlcv_df.iloc[i]["close"]) if i < len(ohlcv_df) else 0.0
                for _, opt in day_options.iterrows():
                    strike = float(opt["strike"])
                    # Skip strikes that are too far from ATM (> 2 strike steps = 100 pts)
                    if spot_price > 0 and abs(strike - spot_price) > 150.0:
                        continue
                    call_price = float(opt["call_mkt_price"])
                    put_price = float(opt["put_mkt_price"])
                    call_mispricing = float(opt["call_mispricing"])
                    put_mispricing = float(opt["put_mispricing"])

                    # Dynamic Epsilon
                    call_eps = engine.friction_model.compute_epsilon(
                        premium=call_price, buffer_multiplier=self.buffer_multiplier
                    )
                    put_eps = engine.friction_model.compute_epsilon(
                        premium=put_price, buffer_multiplier=self.buffer_multiplier
                    )

                    # Long Call when market underprices Call: C_mkt - C_PDE < -call_eps
                    if call_mispricing < -call_eps and call_price > 10.0:
                        notional = call_price * engine.lot_size
                        if notional > current_equity * 0.95:
                            continue  # Skip: exceeds capital
                        active_trade = {
                            "entry_date": current_date,
                            "entry_bar_idx": i,
                            "option_type": "call",
                            "strike": strike,
                            "entry_price": call_price,
                            "quantity": engine.lot_size,
                            "epsilon": call_eps,
                            "signal": f"PDE_CALL_UNDERVALUED_{call_mispricing:.2f}",
                        }
                        break

                    # Long Put when market underprices Put: P_mkt - P_PDE < -put_eps
                    elif put_mispricing < -put_eps and put_price > 10.0:
                        notional = put_price * engine.lot_size
                        if notional > current_equity * 0.95:
                            continue
                        active_trade = {
                            "entry_date": current_date,
                            "entry_bar_idx": i,
                            "option_type": "put",
                            "strike": strike,
                            "entry_price": put_price,
                            "quantity": engine.lot_size,
                            "epsilon": put_eps,
                            "signal": f"PDE_PUT_UNDERVALUED_{put_mispricing:.2f}",
                        }
                        break

        return trades


class HybridFilterStrategy(BaseStrategy):
    """
    Challenger B: Combines Crank-Nicolson PDE mispricing valuation with technical momentum confirmation.
    Only enters when theoretical edge aligns with market momentum.
    """

    def __init__(self, holding_period: int = 5, buffer_multiplier: float = 1.5) -> None:
        super().__init__(name="Challenger_B_Hybrid_QuantMental", holding_period=holding_period)
        self.buffer_multiplier = buffer_multiplier

    def generate_trades(
        self,
        ohlcv_df: pd.DataFrame,
        options_df: pd.DataFrame,
        engine: BacktestEngine,
    ) -> List[Trade]:
        trades: List[Trade] = []
        trade_id = 1
        active_trade: Optional[Dict[str, Any]] = None
        current_equity = engine.initial_capital

        options_grouped = options_df.groupby("date")
        ohlcv_indexed = ohlcv_df.set_index("date")
        dates_list = ohlcv_df["date"].tolist()

        for i, current_date in enumerate(dates_list):
            if current_date not in options_grouped.groups or current_date not in ohlcv_indexed.index:
                continue

            day_options = options_grouped.get_group(current_date)
            ohlcv_row = ohlcv_indexed.loc[current_date]
            rsi = ohlcv_row.get("rsi")
            macd_hist = ohlcv_row.get("macd_hist")

            # 1. Manage Active Trade
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
                elif bars_held >= 2 and abs(current_mispricing) < (active_trade["epsilon"] / 2.0):
                    # BUG FIX #2: Same minimum 2-bar hold for Hybrid strategy.
                    exit_reason = "MEAN_REVERTED"
                elif bars_held >= self.holding_period:
                    exit_reason = "TIME_EXPIRY"

                if exit_reason:
                    qty = active_trade["quantity"]
                    friction_est = engine.friction_model.estimate(
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

            # 2. Check Hybrid Signals
            if active_trade is None and rsi is not None and macd_hist is not None:
                # BUG FIX #4: Same near-ATM restriction for Hybrid.
                spot_price = float(ohlcv_row["close"]) if "close" in ohlcv_row.index else 0.0
                for _, opt in day_options.iterrows():
                    strike = float(opt["strike"])
                    if spot_price > 0 and abs(strike - spot_price) > 150.0:
                        continue
                    call_price = float(opt["call_mkt_price"])
                    put_price = float(opt["put_mkt_price"])
                    call_mispricing = float(opt["call_mispricing"])
                    put_mispricing = float(opt["put_mispricing"])

                    call_eps = engine.friction_model.compute_epsilon(
                        premium=call_price, buffer_multiplier=self.buffer_multiplier
                    )
                    put_eps = engine.friction_model.compute_epsilon(
                        premium=put_price, buffer_multiplier=self.buffer_multiplier
                    )

                    # Hybrid Long Call: PDE Undervalued + Bullish MACD + RSI not overbought
                    if (
                        call_mispricing < -call_eps
                        and macd_hist > 0
                        and rsi < 65.0
                        and call_price > 10.0
                    ):
                        notional = call_price * engine.lot_size
                        if notional > current_equity * 0.95:
                            continue
                        active_trade = {
                            "entry_date": current_date,
                            "entry_bar_idx": i,
                            "option_type": "call",
                            "strike": strike,
                            "entry_price": call_price,
                            "quantity": engine.lot_size,
                            "epsilon": call_eps,
                            "signal": "HYBRID_PDE_UNDERVALUED_MACD_BULL",
                        }
                        break

                    # Hybrid Long Put: PDE Undervalued + Bearish MACD + RSI not oversold
                    elif (
                        put_mispricing < -put_eps
                        and macd_hist < 0
                        and rsi > 35.0
                        and put_price > 10.0
                    ):
                        notional = put_price * engine.lot_size
                        if notional > current_equity * 0.95:
                            continue
                        active_trade = {
                            "entry_date": current_date,
                            "entry_bar_idx": i,
                            "option_type": "put",
                            "strike": strike,
                            "entry_price": put_price,
                            "quantity": engine.lot_size,
                            "epsilon": put_eps,
                            "signal": "HYBRID_PDE_UNDERVALUED_MACD_BEAR",
                        }
                        break

        return trades

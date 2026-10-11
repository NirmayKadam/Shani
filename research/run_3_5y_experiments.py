"""
File Overview: 3.5-Year Experiment Runner (Jan 2021 - Jun 2024).
1. Independent fresh-capital backtests for Periods A, B, C and D (no continuous-run slicing).
2. Next-bar fills, contract-locked marks, pre-expiry square-off, date-dependent STT.
3. Trade-level statistics (net return on premium with bootstrap CI, profit factor,
   return without the largest trade) and a matched puts-only random baseline per cell.
4. Pooled trade breakdown, VIX-regime and friction-stress tables.
Publication figures are produced by research/reproduce_all.py.
"""

import os
import sys
import logging
from datetime import date
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
import yfinance as yf

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from research.models.nifty_market_rules import get_nifty_lot_size, get_rbi_repo_rate, get_stt_rate, Black76Engine
from research.models.friction_model import IndianOptionsFrictionModel
from research.backtest.engine import BacktestEngine, Trade, BacktestResult
from research.analysis.metrics import to_latex_table, to_markdown_table
from research.analysis.trade_stats import (
    bootstrap_mean_ci,
    matched_random_baseline,
    net_return_on_premium,
    percentile_of,
    trade_level_stats,
)

logger = logging.getLogger("Master3_5YRunner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class StrategyContext:
    """
    Lookups shared by every strategy run on one (signal panel, marks) pair. Build it once and
    pass it to generate_trades() when running many variants (e.g. random-baseline draws).

    signal_rows: date -> signal-expiry panel rows (ascending strike), as plain dicts.
    mark_lookup: (date, expiry, strike, type) -> CLOSE (NaN if that contract did not trade).
    mispricing_lookup: (date, expiry, strike, type) -> panel mispricing.
    """

    def __init__(self, options_df: pd.DataFrame, marks_df: Optional[pd.DataFrame] = None) -> None:
        signal_df = options_df[options_df["is_signal_expiry"]] if "is_signal_expiry" in options_df.columns else options_df
        signal_df = signal_df.sort_values(["date", "strike"])
        self.signal_rows: Dict[date, List[Dict[str, Any]]] = {
            d: g.to_dict("records") for d, g in signal_df.groupby("date")
        }
        self.signal_expiry: Dict[date, date] = {d: rows[0]["expiry_date"] for d, rows in self.signal_rows.items()}

        marks = marks_df if marks_df is not None else build_marks(options_df)
        self.mark_lookup: Dict[Tuple[date, date, float, str], float] = {}
        for r in marks.itertuples(index=False):
            self.mark_lookup[(r.date, r.expiry_date, float(r.strike), "call")] = r.call_mkt_price
            self.mark_lookup[(r.date, r.expiry_date, float(r.strike), "put")] = r.put_mkt_price
        self.mispricing_lookup: Dict[Tuple[date, date, float, str], float] = {}
        for r in options_df.itertuples(index=False):
            self.mispricing_lookup[(r.date, r.expiry_date, float(r.strike), "call")] = float(r.call_mispricing)
            self.mispricing_lookup[(r.date, r.expiry_date, float(r.strike), "put")] = float(r.put_mispricing)

        self.listed = set(zip(marks["date"], marks["expiry_date"]))
        sessions = sorted(marks["date"].unique())
        self.session_set = set(sessions)
        self.next_session = dict(zip(sessions[:-1], sessions[1:]))


class RobustBacktestStrategy:
    """
    Standardized strategy executor supporting:
    - Pure Mispricing vs Hybrid Filter vs Retail Baseline vs puts-only random baseline
    - i+1 execution lag
    - Fixed 50-unit sizing
    - Dynamic epsilon with customizable scaling

    Legacy switches (used only to reproduce the pre-correction pipeline for the waterfall):
    - fill_lag=0: fill at the signal bar's own close (same-bar fill).
    - contract_lock=False: price a held position by (date, strike) against whatever expiry
      the panel lists that day, with no pre-expiry square-off; a strike missing from the
      panel is marked at its entry price with zero mispricing.
    Untraded (stale) prices are excluded via the marks table; pass
    build_marks(df, mask_untraded=False) to reproduce the legacy behaviour.
    """

    def __init__(
        self,
        strategy_type: str = "PURE_PDE",  # 'PURE_PDE', 'HYBRID', 'RETAIL', 'RANDOM_PUT'
        holding_period: int = 5,
        buffer_multiplier: float = 1.5,
        stop_loss_pct: float = 0.35,
        take_profit_pct: float = 0.60,
        fixed_units: int = 50,
        scale_entry_epsilon: bool = False,
        friction_multiplier: float = 1.0,
        fill_lag: int = 1,
        contract_lock: bool = True,
        entry_prob: float = 0.0,
        seed: Optional[int] = None,
    ) -> None:
        if fill_lag not in (0, 1):
            raise ValueError("fill_lag must be 0 or 1")
        self.strategy_type = strategy_type
        self.holding_period = holding_period
        self.buffer_multiplier = buffer_multiplier
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.fixed_units = fixed_units
        self.scale_entry_epsilon = scale_entry_epsilon
        self.friction_multiplier = friction_multiplier
        self.fill_lag = fill_lag
        self.contract_lock = contract_lock
        # RANDOM_PUT: on each eligible day, enter with probability entry_prob on a uniformly
        # drawn near-ATM put of the signal expiry; exits, costs and fills match PURE_PDE.
        self.entry_prob = entry_prob
        self.rng = np.random.default_rng(seed)

    def generate_trades(
        self,
        ohlcv_df: pd.DataFrame,
        options_df: pd.DataFrame,
        engine: BacktestEngine,
        marks_df: Optional[pd.DataFrame] = None,
        ctx: Optional[StrategyContext] = None,
    ) -> List[Trade]:
        """
        options_df: signal panel keyed (date, expiry_date, strike). If it has is_signal_expiry,
            new signals are taken only on that expiry; held contracts read their own row.
        marks_df: prices used for fills and marks, from build_marks(). Defaults to the panel.
        ctx: prebuilt StrategyContext (overrides options_df/marks_df lookups).
        """
        ctx = ctx or StrategyContext(options_df, marks_df)
        trades: List[Trade] = []
        trade_id = 1
        active_trade: Optional[Dict[str, Any]] = None
        pending_signal: Optional[Dict[str, Any]] = None
        current_equity = engine.initial_capital
        dates_list = ohlcv_df["date"].tolist()

        def _contract_expiry(d: date, expiry: date) -> Optional[date]:
            # Legacy mode ignores the contract's own expiry and reads whatever the panel lists today
            return expiry if self.contract_lock else ctx.signal_expiry.get(d)

        def _must_square_off(d: date, expiry: date) -> bool:
            # Last session before the contract leaves the marks (legacy panel roll) or before
            # expiry day (full chain). Both follow from the exchange calendar, not future prices.
            if not self.contract_lock:
                return False
            nxt = ctx.next_session.get(d)
            return nxt is None or (nxt, expiry) not in ctx.listed or (expiry - nxt).days < 1

        def _traded_price(d: date, expiry: date, strike: float, opt_type: str) -> Optional[float]:
            """CLOSE if the contract traded that day, else None (a zero-volume CLOSE is stale)."""
            p = ctx.mark_lookup.get((d, _contract_expiry(d, expiry), strike, opt_type))
            return float(p) if p is not None and np.isfinite(p) else None

        # STT is levied on the sell leg, so realized friction uses the exit date's STT rate
        # and the entry threshold uses the signal date's rate.
        f_mult = self.friction_multiplier if self.scale_entry_epsilon else 1.0
        friction_cache: Dict[Tuple[float, float], IndianOptionsFrictionModel] = {}

        def _friction(d: date, mult: float) -> IndianOptionsFrictionModel:
            key = (get_stt_rate(d), mult)
            if key not in friction_cache:
                friction_cache[key] = IndianOptionsFrictionModel(
                    default_lot_size=self.fixed_units, stt_sell_rate=key[0], multiplier=mult
                )
            return friction_cache[key]

        def _try_fill(d: date, bar_idx: int, sig: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            # Fill only on the signal's own contract, only if it traded, and not on its last session.
            fill_price = _traded_price(d, sig["expiry_date"], sig["strike"], sig["option_type"])
            if fill_price is None or fill_price <= 5.0 or _must_square_off(d, sig["expiry_date"]):
                return None
            if fill_price * self.fixed_units > current_equity * 0.95:
                return None
            return {
                "entry_date": d,
                "entry_bar_idx": bar_idx,
                "option_type": sig["option_type"],
                "strike": sig["strike"],
                "expiry_date": sig["expiry_date"],
                "entry_price": fill_price,
                "last_price": fill_price,
                "quantity": self.fixed_units,
                "epsilon": sig["epsilon"],
                "signal": sig["signal"],
            }

        for i, current_date in enumerate(dates_list):
            if current_date not in ctx.session_set:
                continue

            day_rows = ctx.signal_rows.get(current_date, [])
            day_expiry = ctx.signal_expiry.get(current_date)
            row = ohlcv_df.iloc[i]
            rsi = row.get("rsi")
            macd_hist = row.get("macd_hist")

            # 1. Fill Pending Signal from bar i-1 (i+1 execution lag)
            if active_trade is None and pending_signal is not None:
                active_trade = _try_fill(current_date, i, pending_signal)
                pending_signal = None

            # 2. Manage Active Trade
            if active_trade is not None:
                bars_held = i - active_trade["entry_bar_idx"]
                target_strike = active_trade["strike"]
                opt_type = active_trade["option_type"]
                trade_expiry = active_trade["expiry_date"]

                traded = _traded_price(current_date, trade_expiry, target_strike, opt_type)
                # None when the held contract is outside today's panel (mean-reversion exit then waits)
                current_mispricing = ctx.mispricing_lookup.get(
                    (current_date, _contract_expiry(current_date, trade_expiry), target_strike, opt_type)
                )
                if traded is not None:
                    current_price = traded
                    active_trade["last_price"] = traded
                elif not self.contract_lock:
                    # Legacy: a strike missing from today's panel was marked at its entry price with
                    # zero mispricing, which forced a MEAN_REVERTED exit at the entry price
                    current_price = active_trade["entry_price"]
                    current_mispricing = 0.0
                else:
                    # No trade in this contract today: carry the last mark, never a different contract
                    current_price = active_trade["last_price"]

                pnl_per_unit = current_price - active_trade["entry_price"]
                pnl_pct = pnl_per_unit / active_trade["entry_price"] if active_trade["entry_price"] > 0 else 0.0

                exit_reason = None
                if pnl_pct <= -self.stop_loss_pct:
                    exit_reason = "STOP_LOSS"
                elif pnl_pct >= self.take_profit_pct:
                    exit_reason = "TAKE_PROFIT"
                elif (
                    bars_held >= 2
                    and current_mispricing is not None
                    and abs(current_mispricing) < (active_trade["epsilon"] / 2.0)
                    and self.strategy_type != "RETAIL"
                ):
                    exit_reason = "MEAN_REVERTED"
                elif bars_held >= self.holding_period:
                    exit_reason = "TIME_EXPIRY"
                elif _must_square_off(current_date, trade_expiry):
                    exit_reason = "PRE_EXPIRY_SQUAREOFF"

                if exit_reason:
                    qty = active_trade["quantity"]
                    friction_est = _friction(current_date, self.friction_multiplier).estimate(
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
                            expiry_date=trade_expiry,
                        )
                    )
                    current_equity += pnl_net
                    trade_id += 1
                    active_trade = None

            # 3. Check for New Signal at Bar i
            if (
                active_trade is None
                and pending_signal is None
                and day_rows
                and i < len(dates_list) - 1
                and not _must_square_off(current_date, day_expiry)
            ):
                new_signal = self._signal(current_date, day_expiry, day_rows, float(row["close"]), rsi, macd_hist,
                                          _friction(current_date, f_mult))
                if new_signal is not None:
                    if self.fill_lag == 0:
                        # Legacy same-bar fill at the signal bar's close
                        active_trade = _try_fill(current_date, i, new_signal)
                    else:
                        pending_signal = new_signal

        return trades

    def _signal(
        self,
        current_date: date,
        day_expiry: date,
        day_rows: List[Dict[str, Any]],
        spot_price: float,
        rsi: Optional[float],
        macd_hist: Optional[float],
        entry_threshold_model: IndianOptionsFrictionModel,
    ) -> Optional[Dict[str, Any]]:
        base = {"signal_date": current_date, "expiry_date": day_expiry}

        if self.strategy_type == "RETAIL":
            # Retail Baseline (ATM RSI + MACD)
            atm = [r for r in day_rows if r["is_atm"]]
            if not atm or rsi is None or macd_hist is None:
                return None
            atm_row = atm[0]
            # Bullish setup
            if ((rsi > 50.0 and macd_hist > 0) or (rsi <= 45.0 and macd_hist > 0)) and atm_row["call_mkt_price"] > 10.0:
                return {**base, "option_type": "call", "strike": float(atm_row["strike"]), "epsilon": 0.0, "signal": "RSI_MACD_BULL"}
            # Bearish setup
            if ((rsi < 50.0 and macd_hist < 0) or (rsi >= 55.0 and macd_hist < 0)) and atm_row["put_mkt_price"] > 10.0:
                return {**base, "option_type": "put", "strike": float(atm_row["strike"]), "epsilon": 0.0, "signal": "RSI_MACD_BEAR"}
            return None

        near_atm = [r for r in day_rows if abs(float(r["strike"]) - spot_price) <= 150.0]

        if self.strategy_type == "RANDOM_PUT":
            candidates = [r for r in near_atm if r["put_mkt_price"] > 10.0]
            if not candidates or self.rng.random() >= self.entry_prob:
                return None
            pick = candidates[int(self.rng.integers(len(candidates)))]
            put_eps = entry_threshold_model.compute_epsilon(premium=pick["put_mkt_price"], buffer_multiplier=self.buffer_multiplier)
            return {**base, "option_type": "put", "strike": float(pick["strike"]), "epsilon": put_eps, "signal": "RANDOM_PUT"}

        # Model Mispricing (Pure or Hybrid): first qualifying strike in ascending order
        for opt in near_atm:
            strike = float(opt["strike"])
            call_price = float(opt["call_mkt_price"])
            put_price = float(opt["put_mkt_price"])
            call_mispricing = float(opt["call_mispricing"])
            put_mispricing = float(opt["put_mispricing"])
            call_eps = entry_threshold_model.compute_epsilon(premium=call_price, buffer_multiplier=self.buffer_multiplier)
            put_eps = entry_threshold_model.compute_epsilon(premium=put_price, buffer_multiplier=self.buffer_multiplier)

            bull_filter = True
            bear_filter = True
            if self.strategy_type == "HYBRID":
                # Frozen rules (paper Sec. 4 / legacy HybridFilterStrategy): RSI < 65 for calls, RSI > 35 for puts
                bull_filter = macd_hist is not None and macd_hist > 0 and rsi is not None and rsi < 65.0
                bear_filter = macd_hist is not None and macd_hist < 0 and rsi is not None and rsi > 35.0

            if call_mispricing < -call_eps and call_price > 10.0 and bull_filter:
                return {**base, "option_type": "call", "strike": strike, "epsilon": call_eps,
                        "signal": f"CALL_UNDERVALUED_{call_mispricing:.2f}"}
            if put_mispricing < -put_eps and put_price > 10.0 and bear_filter:
                return {**base, "option_type": "put", "strike": strike, "epsilon": put_eps,
                        "signal": f"PUT_UNDERVALUED_{put_mispricing:.2f}"}
        return None


def _load_panel(data_dir: str, stem: str, date_cols: List[str]) -> pd.DataFrame:
    """Read the parquet panel, falling back to the CSV copy when no parquet engine is installed."""
    try:
        df = pd.read_parquet(os.path.join(data_dir, f"{stem}.parquet"))
    except ImportError:
        df = pd.read_csv(os.path.join(data_dir, f"{stem}.csv"))
    for c in date_cols:
        df[c] = pd.to_datetime(df[c]).dt.date
    return df


def build_marks(df: pd.DataFrame, mask_untraded: bool = True) -> pd.DataFrame:
    """
    Marks table keyed (date, expiry_date, strike) with call/put CLOSE prices.
    A price is NaN when that contract had zero volume that day, since the CLOSE is then stale
    (mask_untraded=False keeps every CLOSE, reproducing the legacy pipeline).
    Accepts the wide signal panel or the long full chain.
    """
    if "option_type" in df.columns:
        traded = df[df["contracts"] > 0] if mask_untraded else df
        wide = traded.pivot_table(index=["date", "expiry_date", "strike"], columns="option_type", values="close", aggfunc="first")
        listed = df[["date", "expiry_date", "strike"]].drop_duplicates()
        wide = listed.merge(wide.reset_index(), on=["date", "expiry_date", "strike"], how="left")
        return wide.rename(columns={"call": "call_mkt_price", "put": "put_mkt_price"})[
            ["date", "expiry_date", "strike", "call_mkt_price", "put_mkt_price"]
        ]
    out = df[["date", "expiry_date", "strike"]].copy()
    if mask_untraded and "call_contracts" in df.columns:
        out["call_mkt_price"] = df["call_mkt_price"].where(df["call_contracts"] > 0)
        out["put_mkt_price"] = df["put_mkt_price"].where(df["put_contracts"] > 0)
    else:
        # Legacy panels without volume columns (or legacy mode): every CLOSE is used
        out["call_mkt_price"] = df["call_mkt_price"].astype(float)
        out["put_mkt_price"] = df["put_mkt_price"].astype(float)
    return out


SUB_PERIODS = {
    "A (2021)": (date(2021, 1, 1), date(2021, 12, 31)),
    "B (2022)": (date(2022, 1, 1), date(2022, 12, 31)),
    "C (Jan-Sep 2023)": (date(2023, 1, 1), date(2023, 9, 30)),
    "D (Oct 2023-Jun 2024)": (date(2023, 10, 1), date(2024, 6, 28)),
}
STRATEGIES = {"Pure Mispricing": "PURE_PDE", "Hybrid Filter": "HYBRID", "Retail Baseline": "RETAIL"}
VIX_BANDS = {  # pre-committed Period D quantile bands
    "Low VIX (< 12.6)": lambda v: v < 12.6,
    "Normal VIX (12.6 - 14.5)": lambda v: 12.6 <= v <= 14.5,
    "High VIX (> 14.5)": lambda v: v > 14.5,
}


def load_study_data(data_dir: str, panel: str = "v2") -> Dict[str, Any]:
    """Signal panel, marks and OHLCV for the 3.5-year study."""
    ohlcv_df = _load_panel(data_dir, "nifty_3_5y_daily_ohlcv", date_cols=["date"])
    if panel == "v2":
        # Multi-expiry signal panel + full chain for marks (built by build_3_5_year_dataset.py --from-cache)
        options_df = _load_panel(data_dir, "nifty_3_5y_option_chains_v2", date_cols=["date", "expiry_date"])
        full_chain = pd.read_parquet(os.path.join(data_dir, "nifty_3_5y_full_chain.parquet"))
        for c in ("date", "expiry_date"):
            full_chain[c] = pd.to_datetime(full_chain[c]).dt.date
        marks_df = build_marks(full_chain)
    else:
        # Legacy one-expiry panel (rolls weekly at DTE < 7): marks come from the panel itself
        options_df = _load_panel(data_dir, "nifty_3_5y_option_chains", date_cols=["date", "expiry_date"])
        marks_df = build_marks(options_df)
    return {"ohlcv": ohlcv_df, "panel": options_df, "marks": marks_df}


def _slice(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)


def run_independent_periods(
    data: Dict[str, Any],
    initial_capital: float = 100_000.0,
    random_draws: int = 500,
    seed: int = 12345,
) -> Dict[str, Any]:
    """
    Every strategy-period cell is an independent backtest from fresh capital, so no cell
    depends on the capital path of an earlier period.
    """
    engine = BacktestEngine(initial_capital=initial_capital, lot_size=50, risk_free_rate=get_rbi_repo_rate)
    rows, trade_frames = [], []
    random_returns: Dict[Tuple[str, str], np.ndarray] = {}

    for pname, (a, b) in SUB_PERIODS.items():
        ohlcv_p, panel_p, marks_p = _slice(data["ohlcv"], a, b), _slice(data["panel"], a, b), _slice(data["marks"], a, b)
        ctx = StrategyContext(panel_p, marks_p)
        dates_p = ohlcv_p["date"].tolist()

        def _run_random(entry_prob: float, s: int) -> List[Trade]:
            strat = RobustBacktestStrategy("RANDOM_PUT", entry_prob=entry_prob, seed=s)
            return strat.generate_trades(ohlcv_p, panel_p, engine, ctx=ctx)

        for sname, stype in STRATEGIES.items():
            trades = RobustBacktestStrategy(stype).generate_trades(ohlcv_p, panel_p, engine, ctx=ctx)
            res = engine.calculate_portfolio_metrics(f"{sname} {pname}", trades, dates_p, options_df=marks_p)
            stats = trade_level_stats(trades, initial_capital)
            rb = matched_random_baseline(_run_random, len(trades), initial_capital, n_draws=random_draws, seed=seed)
            random_returns[(pname, sname)] = rb["returns"]
            rows.append(
                {
                    "Period": pname,
                    "Strategy": sname,
                    "Return_Pct": res.total_return_pct,
                    "Sharpe": res.sharpe_ratio,
                    "Max_DD_Pct": res.max_drawdown_pct,
                    **stats,
                    "Random_Mean_Return_Pct": float(np.mean(rb["returns"])) if len(rb["returns"]) else np.nan,
                    "Random_P5_Return_Pct": float(np.percentile(rb["returns"], 5)) if len(rb["returns"]) else np.nan,
                    "Random_P95_Return_Pct": float(np.percentile(rb["returns"], 95)) if len(rb["returns"]) else np.nan,
                    "Random_Mean_Trades": float(np.mean(rb["trade_counts"])) if len(rb["trade_counts"]) else 0.0,
                    "Percentile_vs_Random": percentile_of(res.total_return_pct, rb["returns"]) if len(rb["returns"]) else np.nan,
                }
            )
            t_df = pd.DataFrame([vars(t) for t in trades])
            if not t_df.empty:
                t_df.insert(0, "Strategy", sname)
                t_df.insert(0, "Period", pname)
                trade_frames.append(t_df)
            logger.info(f"{pname} | {sname}: {len(trades)} trades, return {res.total_return_pct:.2f}%")

    trades_all = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    return {"table": pd.DataFrame(rows), "trades": trades_all, "random_returns": random_returns}


def trade_breakdown(trades_all: pd.DataFrame) -> pd.DataFrame:
    """Pooled trades from the independent runs, by strategy, option type and exit reason."""
    records = []
    for (sname, opt_type, exit_sig), g in trades_all.groupby(["Strategy", "option_type", "exit_signal"]):
        rop = g["pnl_net"] / (g["entry_price"] * g["quantity"])
        records.append(
            {
                "Strategy": sname,
                "Option_Type": opt_type,
                "Exit_Signal": exit_sig,
                "Trades": len(g),
                "Net_PnL_INR": round(g["pnl_net"].sum(), 2),
                "RoP_Mean_Pct": round(rop.mean() * 100.0, 2),
                "Win_Rate_Pct": round(100.0 * g["is_win"].mean(), 2),
                "Mean_Holding_Bars": round(g["holding_bars"].mean(), 2),
            }
        )
    return pd.DataFrame(records)


def vix_regime_table(trades_all: pd.DataFrame, vix_by_date: Dict[date, float]) -> pd.DataFrame:
    """Trade-level statistics by India VIX at entry, pooled over the independent period runs."""
    records = []
    for regime, cond in VIX_BANDS.items():
        for sname in STRATEGIES:
            g = trades_all[(trades_all["Strategy"] == sname)
                           & trades_all["entry_date"].map(lambda d: cond(vix_by_date.get(d, np.nan)))]
            rop = (g["pnl_net"] / (g["entry_price"] * g["quantity"])).values
            ci = bootstrap_mean_ci(rop)
            records.append(
                {
                    "VIX_Regime": regime,
                    "Strategy": sname,
                    "Trades": len(g),
                    "Net_PnL_INR": round(g["pnl_net"].sum(), 2),
                    "RoP_Mean_Pct": ci["mean"] * 100.0,
                    "RoP_CI_Lo_Pct": ci["lo"] * 100.0,
                    "RoP_CI_Hi_Pct": ci["hi"] * 100.0,
                    "Win_Rate_Pct": float(g["is_win"].mean() * 100.0) if len(g) else np.nan,
                }
            )
    return pd.DataFrame(records)


def friction_stress_table(data: Dict[str, Any], initial_capital: float = 100_000.0) -> pd.DataFrame:
    """Pure Mispricing under scaled costs, independent per period; trade-level RoP pooled across periods."""
    engine = BacktestEngine(initial_capital=initial_capital, lot_size=50, risk_free_rate=get_rbi_repo_rate)
    contexts = {}
    for pname, (a, b) in SUB_PERIODS.items():
        panel_p, marks_p = _slice(data["panel"], a, b), _slice(data["marks"], a, b)
        contexts[pname] = (_slice(data["ohlcv"], a, b), panel_p, StrategyContext(panel_p, marks_p))
    records = []
    for mult in [1.0, 1.5, 2.0, 3.0]:
        for protocol, scale_eps in [("Epsilon fixed", False), ("Epsilon scaled", True)]:
            pooled, rec = [], {"Multiplier": f"{mult:.1f}x", "Protocol": protocol}
            for pname, (ohlcv_p, panel_p, ctx) in contexts.items():
                strat = RobustBacktestStrategy("PURE_PDE", friction_multiplier=mult, scale_entry_epsilon=scale_eps)
                trades = strat.generate_trades(ohlcv_p, panel_p, engine, ctx=ctx)
                pooled.extend(trades)
                rec[f"Return_{pname.split()[0]}_Pct"] = round(sum(t.pnl_net for t in trades) / initial_capital * 100.0, 2)
            ci = bootstrap_mean_ci(net_return_on_premium(pooled))
            rec.update({"Trades": len(pooled), "RoP_Mean_Pct": ci["mean"] * 100.0,
                        "RoP_CI_Lo_Pct": ci["lo"] * 100.0, "RoP_CI_Hi_Pct": ci["hi"] * 100.0})
            records.append(rec)
    return pd.DataFrame(records)


def fetch_india_vix() -> Dict[date, float]:
    vix_df = yf.download("^INDIAVIX", start="2021-01-01", end="2024-07-02", progress=False)
    if isinstance(vix_df.columns, pd.MultiIndex):
        vix_df.columns = [c[0].lower() for c in vix_df.columns]
    else:
        vix_df.columns = [c.lower() for c in vix_df.columns]
    vix_df = vix_df.reset_index().rename(columns={"Date": "date"})
    return dict(zip(pd.to_datetime(vix_df["date"]).dt.date, vix_df["close"].astype(float)))


def run_master_3_5y_experiments(panel: str = "v2", random_draws: int = 500) -> Dict[str, Any]:
    logger.info("=" * 75)
    logger.info("3.5-YEAR EXPERIMENTS (2021 - 2024): INDEPENDENT FRESH-CAPITAL PERIOD RUNS")
    logger.info("=" * 75)

    base_dir = os.path.abspath(os.path.dirname(__file__))
    data_dir = os.path.join(base_dir, "data", "raw")
    tables_dir = os.path.join(base_dir, "output", "tables")
    trade_logs_dir = os.path.join(base_dir, "output", "trade_logs")
    os.makedirs(tables_dir, exist_ok=True)
    os.makedirs(trade_logs_dir, exist_ok=True)
    tag = "_3_5y_v2" if panel == "v2" else "_3_5y"

    data = load_study_data(data_dir, panel)
    logger.info(f"Panel '{panel}': {len(data['panel'])} signal rows, {len(data['marks'])} mark rows")

    periods = run_independent_periods(data, random_draws=random_draws)
    period_df = periods["table"]
    period_df.to_csv(os.path.join(tables_dir, f"period_results{tag}.csv"), index=False)
    periods["trades"].to_csv(os.path.join(trade_logs_dir, f"all_trades{tag}.csv"), index=False)

    breakdown_df = trade_breakdown(periods["trades"])
    breakdown_df.to_csv(os.path.join(tables_dir, f"trade_breakdown{tag}.csv"), index=False)

    vix_df = vix_regime_table(periods["trades"], fetch_india_vix())
    vix_df.to_csv(os.path.join(tables_dir, f"vix_regime_analysis{tag}.csv"), index=False)

    stress_df = friction_stress_table(data)
    stress_df.to_csv(os.path.join(tables_dir, f"friction_stress_test{tag}.csv"), index=False)

    for title, df in [("PERIOD RESULTS (independent fresh-capital runs)", period_df),
                      ("TRADE BREAKDOWN (pooled)", breakdown_df),
                      ("VIX REGIMES (trade-level, pooled)", vix_df),
                      ("FRICTION STRESS (Pure Mispricing)", stress_df)]:
        print(f"\n{title}:\n{to_markdown_table(df)}")

    return {"periods": periods, "breakdown": breakdown_df, "vix": vix_df, "stress": stress_df}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", choices=["v2", "legacy"], default="v2",
                        help="v2: multi-expiry panel + full-chain marks; legacy: original one-expiry panel")
    parser.add_argument("--random-draws", type=int, default=500)
    args = parser.parse_args()
    run_master_3_5y_experiments(panel=args.panel, random_draws=args.random_draws)

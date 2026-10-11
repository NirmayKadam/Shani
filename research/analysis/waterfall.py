"""
File Overview: Correction waterfall on the original 180-session sample (Oct 2023 - Jun 2024).

Starts from the headline result (+49.57%, Crank-Nicolson PDE, same-bar fills) and applies one
correction at a time, cumulatively, so each row shows how much apparent profit that fix removed:

    S0  Original: PDE fair value (spot, q = 0), same-bar fill, legacy panel     [strategies.py]
    S1  + closed-form Black-Scholes at the same surface IV (removes grid error)  [strategies.py]
    S2  + Black-76 with ATM-parity forward on a consistent CLOSE price field
          (removes the carry bias and the SETTLE/CLOSE mix)
    S3  + next-bar fill (signal at close t, fill at close t+1)
    S4  + contract lock (positions marked on their own expiry, squared off before the roll)
    S5  + no stale prices (zero-volume CLOSEs excluded) and daily MTM accounting
    S6  + full-chain data (signal expiry >= 14 DTE, traded-only IV inputs)

S2 is run with both the legacy strategy class and RobustBacktestStrategy in legacy mode
(fill_lag=0, contract_lock=False, unmasked marks) to show the two produce the same trades,
so the switch of code path between S1 and S2 contributes nothing.
"""

import os
from datetime import date
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from domains.analytics.domain.services.bsm_calculator import BsmCalculatorDomainService
from research.analysis.trade_stats import bootstrap_mean_ci, net_return_on_premium
from research.backtest.engine import BacktestEngine, Trade
from research.backtest.strategies import PDEMispricingStrategy
from research.models.nifty_market_rules import get_rbi_repo_rate
from research.run_3_5y_experiments import RobustBacktestStrategy, StrategyContext, _load_panel, build_marks

INITIAL_CAPITAL = 100_000.0
LEGACY_RATE = 0.065  # flat rate used by the original 180-day pipeline


def _row(step: str, description: str, trades: List[Trade], dates: List[date], marks: pd.DataFrame = None) -> Dict[str, Any]:
    step_engine = BacktestEngine(INITIAL_CAPITAL, 50)  # original: exit-only equity, flat 6.5% hurdle
    res_step = step_engine.calculate_portfolio_metrics(step, trades, dates)
    rop = net_return_on_premium(trades)
    ci = bootstrap_mean_ci(rop)
    out = {
        "Step": step,
        "Correction": description,
        "Trades": len(trades),
        "Puts": sum(t.option_type == "put" for t in trades),
        "Return_Pct": round(sum(t.pnl_net for t in trades) / INITIAL_CAPITAL * 100.0, 2),
        "Win_Rate_Pct": res_step.win_rate,
        "RoP_Mean_Pct": round(ci["mean"] * 100.0, 2),
        "RoP_CI_Lo_Pct": round(ci["lo"] * 100.0, 2),
        "RoP_CI_Hi_Pct": round(ci["hi"] * 100.0, 2),
        "Sharpe_Step_Legacy": res_step.sharpe_ratio,
        "Sharpe_MTM": np.nan,
        "Max_DD_MTM_Pct": np.nan,
    }
    if marks is not None:
        mtm_engine = BacktestEngine(INITIAL_CAPITAL, 50, risk_free_rate=get_rbi_repo_rate)
        res_mtm = mtm_engine.calculate_portfolio_metrics(step, trades, dates, options_df=marks)
        out["Sharpe_MTM"] = res_mtm.sharpe_ratio
        out["Max_DD_MTM_Pct"] = res_mtm.max_drawdown_pct
    return out


def run_waterfall(data_dir: str) -> Dict[str, Any]:
    # --- Legacy 180-day inputs (exactly what produced the headline) ---
    legacy_ohlcv = _load_panel(data_dir, "nifty_daily_ohlcv", date_cols=["date"])
    legacy_panel = _load_panel(data_dir, "nifty_option_chains", date_cols=["date"])
    dates = legacy_ohlcv["date"].tolist()
    date_set = set(dates)
    legacy_engine = BacktestEngine(INITIAL_CAPITAL, 50)

    rows: List[Dict[str, Any]] = []

    t0 = PDEMispricingStrategy(holding_period=5, buffer_multiplier=1.5).generate_trades(legacy_ohlcv, legacy_panel, legacy_engine)
    rows.append(_row("S0", "Original: Crank-Nicolson PDE, spot with q=0, same-bar fill", t0, dates))

    bs_panel = legacy_panel.copy()
    bs_call = [BsmCalculatorDomainService.calculate_price(spot=r.spot, strike=r.strike, expiry_years=r.expiry_years,
               rate=LEGACY_RATE, volatility=r.surface_iv, option_type="call") for r in bs_panel.itertuples()]
    bs_put = [BsmCalculatorDomainService.calculate_price(spot=r.spot, strike=r.strike, expiry_years=r.expiry_years,
              rate=LEGACY_RATE, volatility=r.surface_iv, option_type="put") for r in bs_panel.itertuples()]
    bs_panel["call_mispricing"] = (bs_panel["call_mkt_price"] - np.array(bs_call)).round(4)
    bs_panel["put_mispricing"] = (bs_panel["put_mkt_price"] - np.array(bs_put)).round(4)
    t1 = PDEMispricingStrategy(holding_period=5, buffer_multiplier=1.5).generate_trades(legacy_ohlcv, bs_panel, legacy_engine)
    rows.append(_row("S1", "+ closed-form Black-Scholes at the same surface IV (no PDE grid error)", t1, dates))

    # --- Corrected pricing on the same 180 sessions ---
    ohlcv = _load_panel(data_dir, "nifty_3_5y_daily_ohlcv", date_cols=["date"])
    ohlcv = ohlcv[ohlcv["date"].isin(date_set)].reset_index(drop=True)
    b76_panel = _load_panel(data_dir, "nifty_3_5y_option_chains", date_cols=["date", "expiry_date"])
    b76_panel = b76_panel[b76_panel["date"].isin(date_set)].reset_index(drop=True)

    t2_legacy_class = PDEMispricingStrategy(holding_period=5, buffer_multiplier=1.5).generate_trades(ohlcv, b76_panel, legacy_engine)
    ctx_unmasked = StrategyContext(b76_panel, build_marks(b76_panel, mask_untraded=False))
    t2 = RobustBacktestStrategy("PURE_PDE", fill_lag=0, contract_lock=False).generate_trades(ohlcv, b76_panel, legacy_engine, ctx=ctx_unmasked)
    bridge = {
        "legacy_class_trades": len(t2_legacy_class),
        "legacy_class_return_pct": round(sum(t.pnl_net for t in t2_legacy_class) / INITIAL_CAPITAL * 100.0, 2),
        "robust_legacy_mode_trades": len(t2),
        "robust_legacy_mode_return_pct": round(sum(t.pnl_net for t in t2) / INITIAL_CAPITAL * 100.0, 2),
    }
    rows.append(_row("S2", "+ Black-76 with ATM-parity forward on CLOSE prices (no carry bias)", t2, dates))

    t3 = RobustBacktestStrategy("PURE_PDE", fill_lag=1, contract_lock=False).generate_trades(ohlcv, b76_panel, legacy_engine, ctx=ctx_unmasked)
    rows.append(_row("S3", "+ next-bar fill", t3, dates))

    marks_unmasked = build_marks(b76_panel, mask_untraded=False)
    t4 = RobustBacktestStrategy("PURE_PDE").generate_trades(ohlcv, b76_panel, legacy_engine, ctx=ctx_unmasked)
    rows.append(_row("S4", "+ contract lock and pre-roll square-off", t4, dates, marks=marks_unmasked))

    marks_masked = build_marks(b76_panel)
    t5 = RobustBacktestStrategy("PURE_PDE").generate_trades(ohlcv, b76_panel, legacy_engine, ctx=StrategyContext(b76_panel, marks_masked))
    rows.append(_row("S5", "+ no stale (zero-volume) prices, daily MTM accounting", t5, dates, marks=marks_masked))

    v2_panel = _load_panel(data_dir, "nifty_3_5y_option_chains_v2", date_cols=["date", "expiry_date"])
    v2_panel = v2_panel[v2_panel["date"].isin(date_set)].reset_index(drop=True)
    full_chain = pd.read_parquet(os.path.join(data_dir, "nifty_3_5y_full_chain.parquet"))
    for c in ("date", "expiry_date"):
        full_chain[c] = pd.to_datetime(full_chain[c]).dt.date
    v2_marks = build_marks(full_chain[full_chain["date"].isin(date_set)])
    t6 = RobustBacktestStrategy("PURE_PDE").generate_trades(ohlcv, v2_panel, legacy_engine, ctx=StrategyContext(v2_panel, v2_marks))
    rows.append(_row("S6", "+ full-chain data (signal expiry >= 14 DTE, traded-only IV inputs)", t6, dates, marks=v2_marks))

    df = pd.DataFrame(rows)
    df["Delta_Return_Pct"] = df["Return_Pct"].diff().round(2)

    # Price-field audit for S2: how often the legacy panel's price differs from CLOSE
    leg = legacy_panel.merge(b76_panel, on=["date", "strike"], suffixes=("_legacy", "_close"))
    price_field = {
        "overlap_rows": len(leg),
        "call_price_differs_share": float((leg["call_mkt_price_legacy"] - leg["call_mkt_price_close"]).abs().gt(0.05).mean()),
        "put_price_differs_share": float((leg["put_mkt_price_legacy"] - leg["put_mkt_price_close"]).abs().gt(0.05).mean()),
    }
    return {"table": df, "bridge": bridge, "price_field": price_field,
            "trades": {"S0": t0, "S1": t1, "S2": t2, "S3": t3, "S4": t4, "S5": t5, "S6": t6}}

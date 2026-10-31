"""
Loads the frozen research outputs (tag paper-audit-v1) and derives every number the lab
documents quote. Nothing here is typed by hand: each value traces to a generated file.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RESEARCH = os.path.join(REPO, "research")
PAPER_OUT = os.path.join(RESEARCH, "output", "paper")
TABLES = os.path.join(PAPER_OUT, "tables")
DATA_RAW = os.path.join(RESEARCH, "data", "raw")

PERIODS = ["A (2021)", "B (2022)", "C (Jan-Sep 2023)", "D (Oct 2023-Jun 2024)"]
STRATS = ["Pure Mispricing", "Hybrid Filter", "Retail Baseline"]


@dataclass
class LabData:
    numbers: Dict[str, str]
    manifest: Dict[str, Any]
    phase0: Dict[str, float]
    periods: pd.DataFrame
    trades: pd.DataFrame
    waterfall: pd.DataFrame
    signal: pd.DataFrame
    signal_legacy: pd.DataFrame
    obs: pd.DataFrame
    breakdown: pd.DataFrame
    vix: pd.DataFrame
    stress: pd.DataFrame
    facts: Dict[str, Any] = field(default_factory=dict)

    def cell(self, period: str, strategy: str, col: str) -> float:
        return float(self.periods[(self.periods["Period"] == period) & (self.periods["Strategy"] == strategy)][col].iloc[0])


def _json(path: str) -> Dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def confusion(obs: pd.DataFrame) -> Dict[str, Any]:
    """
    The mispricing signal as a binary classifier on near-ATM signal-expiry puts.
    Predicted positive: mispricing < -epsilon (the entry signal).
    Actual positive: the put's delta-hedged P&L from the next close to the following close
    beats the same-date cross-sectional mean by more than its round-trip cost, i.e. a trader
    filling at the next close would have earned its costs back on relative value.
    """
    o = obs.dropna(subset=["hedged_t1_t2"]).copy()
    o["excess_t1_t2"] = o["hedged_t1_t2"] - o.groupby("date")["hedged_t1_t2"].transform("mean")
    o["excess_t0_t1"] = o["hedged_t0_t1"] - o.groupby("date")["hedged_t0_t1"].transform("mean")
    pred = (o["group"] == "undervalued").values
    out = {"n": len(o)}
    for h in ("t1_t2", "t0_t1"):
        actual = (o[f"excess_{h}"] > o["round_trip_cost"]).values
        tp = int((pred & actual).sum()); fp = int((pred & ~actual).sum())
        fn = int((~pred & actual).sum()); tn = int((~pred & ~actual).sum())
        out[h] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "actual_pos": int(actual.sum())}
    return out


def metrics(tp: float, fp: float, fn: float, tn: float) -> Dict[str, float]:
    n = tp + fp + fn + tn
    acc = (tp + tn) / n
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else float("nan")
    return {"accuracy": acc, "precision": prec, "recall": rec, "f1": f1, "error": 1 - acc}


def baseline_confusions(cm: Dict[str, int], n: int) -> Dict[str, Dict[str, float]]:
    """Expected counts for a random flag at the signal's rate, and for flagging every observation."""
    k = cm["tp"] + cm["fp"]          # number flagged by the signal
    p = cm["actual_pos"]             # number of actual positives
    rate = k / n
    rand = {"tp": rate * p, "fp": rate * (n - p), "fn": (1 - rate) * p, "tn": (1 - rate) * (n - p)}
    always = {"tp": p, "fp": n - p, "fn": 0, "tn": 0}
    return {"random": rand, "always": always}


def time_backtests(reps: int = 3) -> Dict[str, float]:
    """Wall-clock seconds to backtest all four periods, per strategy (lookup context built once)."""
    sys.path.insert(0, REPO)
    from research.backtest.engine import BacktestEngine
    from research.run_3_5y_experiments import SUB_PERIODS, RobustBacktestStrategy, StrategyContext, _slice, load_study_data

    data = load_study_data(DATA_RAW, "v2")
    engine = BacktestEngine(100_000.0, 50)
    ctxs = {}
    for pname, (a, b) in SUB_PERIODS.items():
        panel_p = _slice(data["panel"], a, b)
        ctxs[pname] = (_slice(data["ohlcv"], a, b), panel_p, StrategyContext(panel_p, _slice(data["marks"], a, b)))
    out = {}
    for label, kw in [("PURE_PDE", {}), ("HYBRID", {}), ("RETAIL", {}), ("RANDOM_PUT", {"entry_prob": 0.2, "seed": 1})]:
        stype = label
        best = float("inf")
        for _ in range(reps):
            t0 = time.perf_counter()
            for ohlcv_p, panel_p, ctx in ctxs.values():
                RobustBacktestStrategy(stype, **kw).generate_trades(ohlcv_p, panel_p, engine, ctx=ctx)
            best = min(best, time.perf_counter() - t0)
        out[label] = best
    return out


def load() -> LabData:
    d = LabData(
        numbers=_json(os.path.join(PAPER_OUT, "numbers.json")),
        manifest=_json(os.path.join(PAPER_OUT, "manifest.json")),
        phase0=_json(os.path.join(RESEARCH, "output", "phase0_diagnostics", "00_summary.json")),
        periods=pd.read_csv(os.path.join(TABLES, "period_results.csv")),
        trades=pd.read_csv(os.path.join(RESEARCH, "output", "trade_logs", "all_trades_3_5y_v2.csv")),
        waterfall=pd.read_csv(os.path.join(TABLES, "waterfall_180d.csv")),
        signal=pd.read_csv(os.path.join(TABLES, "signal_test_v2.csv")),
        signal_legacy=pd.read_csv(os.path.join(TABLES, "signal_test_legacy.csv")),
        obs=pd.read_csv(os.path.join(TABLES, "signal_observations_v2.csv")),
        breakdown=pd.read_csv(os.path.join(TABLES, "trade_breakdown.csv")),
        vix=pd.read_csv(os.path.join(TABLES, "vix_regime.csv")),
        stress=pd.read_csv(os.path.join(TABLES, "friction_stress.csv")),
    )
    d.trades["rop_pct"] = d.trades["pnl_net"] / (d.trades["entry_price"] * d.trades["quantity"]) * 100.0
    ohlcv = pd.read_csv(os.path.join(DATA_RAW, "nifty_3_5y_daily_ohlcv.csv"))
    d.facts = {
        "index_sessions": int(len(ohlcv)),
        "first_date": str(ohlcv["date"].min()),
        "last_date": str(ohlcv["date"].max()),
        "full_chain_rows": pq.ParquetFile(os.path.join(DATA_RAW, "nifty_3_5y_full_chain.parquet")).metadata.num_rows,
        "signal_panel_rows": pq.ParquetFile(os.path.join(DATA_RAW, "nifty_3_5y_option_chains_v2.parquet")).metadata.num_rows,
        "signal_panel_expiries": int(pd.read_parquet(os.path.join(DATA_RAW, "nifty_3_5y_option_chains_v2.parquet"),
                                                     columns=["expiry_date"])["expiry_date"].nunique()),
        "legacy_180_rows": int(len(pd.read_csv(os.path.join(DATA_RAW, "nifty_option_chains.csv")))),
        "bhavcopy_files": d.manifest.get("bhavcopy_files"),
        # sessions with option data (one index session has no Bhavcopy file)
        "sessions": int(d.manifest.get("bhavcopy_files")),
        "random_draws": int(d.numbers["RandomDraws"]),
        "commit": d.manifest["git_commit"][:7],
    }
    cm = confusion(d.obs)
    d.facts["confusion"] = cm
    d.facts["baselines"] = baseline_confusions(cm["t1_t2"], cm["n"])
    d.facts["baselines_t0"] = baseline_confusions(cm["t0_t1"], cm["n"])
    d.facts["timing_s"] = time_backtests()
    return d


def fmt(x: float, d: int = 2, signed: bool = False) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:+.{d}f}" if signed else f"{x:.{d}f}"


def describe(values) -> Dict[str, float]:
    v = np.asarray(values, dtype=float)
    return {"mean": v.mean(), "median": np.median(v), "var": v.var(ddof=1), "sd": v.std(ddof=1),
            "min": v.min(), "max": v.max(), "n": len(v)}

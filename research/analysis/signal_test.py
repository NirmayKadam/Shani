"""
File Overview: Delta-hedged test of the mispricing signal, separate from any trading strategy.

The signal is a relative-value gap between an option's market price and its surface fair value.
An unhedged long put adds index direction and time decay on top of that gap. Here each
signal is measured on its own: the next-bar change in the put price minus delta times the
change in the forward, compared with the round-trip cost per unit.

    h(t -> t+1) = [P(t+1) - P(t)] - Delta_F(t) * [F(t+1) - F(t)]

Delta_F is the Black-76 put delta with respect to the forward, at the surface IV. The forward
is S * exp(r T) from the index close, not the parity-implied forward, so the hedge does not
reuse the closing option prices the signal is built from.

Two horizons are reported:
- signal-close -> next close (t -> t+1): is there any mean reversion at all, before costs?
- next close -> close after (t+1 -> t+2): the part a trader filling at the next close could capture.

If undervalued puts (mispricing < -eps) mean-revert, h > 0 for them and h < 0 for rich puts.
"""

from datetime import date
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr

from research.analysis.trade_stats import bootstrap_mean_ci
from research.models.friction_model import IndianOptionsFrictionModel
from research.models.nifty_market_rules import get_rbi_repo_rate, get_stt_rate


def _put_delta_forward(forward: float, strike: float, t: float, r: float, sigma: float) -> float:
    t = max(t, 1e-6)
    sigma = max(sigma, 1e-6)
    d1 = (np.log(forward / strike) + 0.5 * sigma ** 2 * t) / (sigma * np.sqrt(t))
    return float(-np.exp(-r * t) * norm.cdf(-d1))


def collect_signal_observations(
    panel: pd.DataFrame,
    marks: pd.DataFrame,
    ohlcv: pd.DataFrame,
    buffer_multiplier: float = 1.5,
    max_distance: float = 150.0,
    lot_units: int = 50,
) -> pd.DataFrame:
    """One row per (date, near-ATM signal-expiry put) with both hedged next-bar P&Ls."""
    signal = panel[panel["is_signal_expiry"]] if "is_signal_expiry" in panel.columns else panel
    put_px = {
        (r.date, r.expiry_date, float(r.strike)): r.put_mkt_price
        for r in marks.itertuples(index=False)
        if np.isfinite(r.put_mkt_price)
    }
    spot = dict(zip(ohlcv["date"], ohlcv["close"].astype(float)))
    sessions = ohlcv["date"].tolist()
    nxt = dict(zip(sessions[:-1], sessions[1:]))
    friction_cache: Dict[float, IndianOptionsFrictionModel] = {}

    def _friction(d: date) -> IndianOptionsFrictionModel:
        rate = get_stt_rate(d)
        if rate not in friction_cache:
            friction_cache[rate] = IndianOptionsFrictionModel(default_lot_size=lot_units, stt_sell_rate=rate)
        return friction_cache[rate]

    rows: List[Dict] = []
    for r in signal.itertuples(index=False):
        d0, exp, k = r.date, r.expiry_date, float(r.strike)
        s0 = spot.get(d0)
        if s0 is None or abs(k - s0) > max_distance or r.put_mkt_price <= 10.0:
            continue
        d1 = nxt.get(d0)
        if d1 is None or (exp - d1).days < 1:
            continue
        p0, p1 = put_px.get((d0, exp, k)), put_px.get((d1, exp, k))
        if p0 is None or p1 is None:
            continue
        rate = get_rbi_repo_rate(d0)
        t0, t1 = (exp - d0).days / 365.0, (exp - d1).days / 365.0
        f0, f1 = s0 * np.exp(rate * t0), spot[d1] * np.exp(rate * t1)
        delta0 = _put_delta_forward(f0, k, t0, rate, r.surface_iv)
        h01 = (p1 - p0) - delta0 * (f1 - f0)

        h12 = np.nan
        d2 = nxt.get(d1)
        if d2 is not None and (exp - d2).days >= 1:
            p2 = put_px.get((d2, exp, k))
            if p2 is not None:
                t2 = (exp - d2).days / 365.0
                f2 = spot[d2] * np.exp(rate * t2)
                delta1 = _put_delta_forward(f1, k, t1, rate, r.surface_iv)
                h12 = (p2 - p1) - delta1 * (f2 - f1)

        eps = _friction(d0).compute_epsilon(premium=r.put_mkt_price, buffer_multiplier=buffer_multiplier)
        mis = float(r.put_mispricing)
        rows.append(
            {
                "date": d0,
                "expiry_date": exp,
                "strike": k,
                "put_price": p0,
                "put_mispricing": mis,
                "epsilon": eps,
                "group": "undervalued" if mis < -eps else ("rich" if mis > eps else "inside_band"),
                "hedged_t0_t1": h01,
                "hedged_t1_t2": h12,
                "round_trip_cost": _friction(d1).estimate(premium=p1, lot_size=lot_units).total_round_trip,
            }
        )
    return pd.DataFrame(rows)


def summarize_signal_test(
    obs: pd.DataFrame, periods: Dict[str, Tuple[date, date]], seed: int = 0
) -> pd.DataFrame:
    """Per period and group: mean hedged P&L with date-clustered bootstrap CIs, versus cost."""
    records = []
    for pname, (a, b) in periods.items():
        po = obs[(obs["date"] >= a) & (obs["date"] <= b)]
        rho = spearmanr(po["put_mispricing"], po["hedged_t0_t1"]).correlation if len(po) > 2 else np.nan
        for group in ("undervalued", "rich", "all"):
            g = po if group == "all" else po[po["group"] == group]
            c01 = bootstrap_mean_ci(g["hedged_t0_t1"].values, clusters=g["date"].astype(str).values, seed=seed)
            g12 = g.dropna(subset=["hedged_t1_t2"])
            c12 = bootstrap_mean_ci(g12["hedged_t1_t2"].values, clusters=g12["date"].astype(str).values, seed=seed)
            records.append(
                {
                    "Period": pname,
                    "Group": group,
                    "N": len(g),
                    "Dates": g["date"].nunique(),
                    "Hedged_t0_t1_Mean": c01["mean"],
                    "Hedged_t0_t1_CI_Lo": c01["lo"],
                    "Hedged_t0_t1_CI_Hi": c01["hi"],
                    "Hedged_t1_t2_Mean": c12["mean"],
                    "Hedged_t1_t2_CI_Lo": c12["lo"],
                    "Hedged_t1_t2_CI_Hi": c12["hi"],
                    "Round_Trip_Cost_Mean": float(g["round_trip_cost"].mean()) if len(g) else np.nan,
                    "Spearman_Mispricing_vs_t0_t1": rho,
                }
            )
    df = pd.DataFrame(records)
    # Hedged long puts bleed theta whatever the signal, so the relevant edge is the excess
    # over all near-ATM puts in the same period (point estimate).
    base = df[df["Group"] == "all"].set_index("Period")
    for h in ("t0_t1", "t1_t2"):
        df[f"Excess_{h}_vs_All"] = df[f"Hedged_{h}_Mean"] - df["Period"].map(base[f"Hedged_{h}_Mean"])
    return df

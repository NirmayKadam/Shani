"""
File Overview: Regenerates every table, figure and number used in the paper, and records the
configuration, code version and data hashes that produced them.

    python research/reproduce_all.py [--random-draws 500] [--bhavcopy-dir PATH]
    python research/reproduce_all.py --tables-only   # re-render from saved CSVs

Inputs (research/data/raw/):
    nifty_daily_ohlcv, nifty_option_chains            legacy 180-session sample (Oct 2023 - Jun 2024)
    nifty_3_5y_daily_ohlcv, nifty_3_5y_option_chains  legacy one-expiry 3.5-year panel
    nifty_3_5y_option_chains_v2, nifty_3_5y_full_chain  full-chain rebuild
        (python research/data/build_3_5_year_dataset.py --from-cache --bhavcopy-dir PATH)

Outputs (research/output/paper/):
    tables/*.tex, tables/*.csv   paper tables (\\input-ready, booktabs)
    figures/*.pdf, figures/*.png
    numbers.tex                  \\newcommand macros for every number quoted in the text
    manifest.json                config, git commit, package versions, input SHA-256
"""

import argparse
import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
from datetime import date, datetime
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"axes.grid": False, "font.family": "sans-serif"})

from research.analysis.signal_test import collect_signal_observations, summarize_signal_test
from research.analysis.waterfall import run_waterfall
from research.phase0_diagnostics import run_phase0_diagnostics
from research.run_3_5y_experiments import SUB_PERIODS, load_study_data, run_master_3_5y_experiments

logger = logging.getLogger("ReproduceAll")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
OUT_DIR = os.path.join(BASE_DIR, "output", "paper")
TABLES_DIR = os.path.join(OUT_DIR, "tables")
FIGURES_DIR = os.path.join(OUT_DIR, "figures")

CONFIG = {
    "initial_capital_inr": 100_000,
    "units_per_trade": 50,
    "holding_period_bars": 5,
    "stop_loss_pct": 35,
    "take_profit_pct": 60,
    "epsilon_buffer_multiplier": 1.5,
    "mean_reversion_exit": "|mispricing| < epsilon/2 after >= 2 bars",
    "near_atm_max_distance_pts": 150,
    "strike_choice": "first qualifying strike in ascending order (unchanged from the original rules)",
    "fill": "next-bar close (signal at close t, fill at close t+1), contract must have traded",
    "max_notional_share_of_equity": 0.95,
    "signal_expiry_min_dte_v2": 14,
    "panel_dte_range_v2": [2, 45],
    "full_chain_filter": "0 <= DTE <= 60, |K/S - 1| <= 12%",
    "iv_inputs_v2": "traded contracts only (zero-volume CLOSE is stale)",
    "costs": "STT by date (0.05% before 2023-04-01, then 0.0625%), exchange 0.05%, stamp 0.003%, SEBI, "
             "GST 18%, INR 20/order, half-spread 0.5% of premium",
    "sharpe_hurdle": "RBI repo-rate step function (idle cash earns nothing)",
    "periods": {k: [str(a), str(b)] for k, (a, b) in SUB_PERIODS.items()},
    "period_runs": "independent backtests from fresh capital per period",
    "bootstrap_resamples": 10_000,
    "bootstrap_ci": "95% percentile",
    "random_baseline": "puts-only, uniform near-ATM strike of the signal expiry, same fills/exits/costs, "
                       "entry probability calibrated to the strategy's trade count",
    "random_baseline_seed": 12345,
    "hybrid_rsi_bands": "call RSI < 65, put RSI > 35",
    "retail_rules": "call: (RSI > 50 or RSI <= 45) and MACD hist > 0; put: (RSI < 50 or RSI >= 55) and MACD hist < 0",
    "vix_bands": "< 12.6, 12.6-14.5, > 14.5 (Period D quantiles)",
}

# Reference palette (dataviz skill), light mode: validated slots
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
POS, NEG = "#2a78d6", "#e34948"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=BASE_DIR, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def _style_axes(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelcolor=INK2, labelsize=8)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _save(fig, name: str) -> None:
    fig.savefig(os.path.join(FIGURES_DIR, f"{name}.pdf"), bbox_inches="tight")
    fig.savefig(os.path.join(FIGURES_DIR, f"{name}.png"), dpi=300, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------- figures

def figure_waterfall(wf: pd.DataFrame) -> None:
    labels = [
        "S0  Original (PDE, same-bar fill)",
        "S1  + closed-form pricing",
        "S2  + forward-consistent pricing",
        "S3  + next-bar fill",
        "S4  + contract lock",
        "S5  + no stale prices, MTM",
        "S6  + full-chain data",
    ]
    vals = wf["Return_Pct"].values
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    y = np.arange(len(vals))[::-1]
    ax.barh(y, vals, height=0.62, color=[POS if v >= 0 else NEG for v in vals], edgecolor="white", linewidth=1)
    ax.axvline(0, color=AXIS, linewidth=1)
    for yi, v, n in zip(y, vals, wf["Trades"].values):
        # Labels sit right of the bar end for gains and right of zero for losses, clear of the axis labels
        ax.text(max(v, 0) + 1.2, yi, f"{v:+.1f}%  ({n} trades)", va="center", ha="left", fontsize=7.5, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8, color=INK)
    ax.set_xlabel("Net return on INR 1 lakh, 180 sessions (%)", fontsize=8, color=INK2)
    lo, hi = min(vals.min(), 0), max(vals.max(), 0)
    ax.set_xlim(lo - 4, hi + 26)
    _style_axes(ax)
    ax.tick_params(axis="y", length=0)
    _save(fig, "fig1_correction_waterfall")


def figure_period_vs_random(period_df: pd.DataFrame) -> None:
    periods = list(SUB_PERIODS)
    strategies = ["Pure Mispricing", "Hybrid Filter", "Retail Baseline"]
    fig, axes = plt.subplots(1, len(periods), figsize=(7.0, 2.8), sharey=True)
    for ax, pname in zip(axes, periods):
        for j, sname in enumerate(strategies):
            r = period_df[(period_df["Period"] == pname) & (period_df["Strategy"] == sname)].iloc[0]
            ax.vlines(j, r["Random_P5_Return_Pct"], r["Random_P95_Return_Pct"], color=GRID, linewidth=7, zorder=1)
            ax.hlines(r["Random_Mean_Return_Pct"], j - 0.18, j + 0.18, color=MUTED, linewidth=1.2, zorder=2)
            ax.scatter(j, r["Return_Pct"], s=42, color=SERIES[j], edgecolor="white", linewidth=1.2, zorder=3,
                       label=sname if pname == periods[0] else None)
        ax.axhline(0, color=AXIS, linewidth=0.8, zorder=0)
        ax.set_xticks(range(len(strategies)))
        ax.set_xticklabels(["Pure", "Hybrid", "Retail"], fontsize=7.5, color=INK2)
        ax.set_title(pname, fontsize=8, color=INK)
        ax.spines[["top", "right"]].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(AXIS)
        ax.tick_params(colors=MUTED, labelcolor=INK2, labelsize=7.5)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.set_xlim(-0.6, len(strategies) - 0.4)
    axes[0].set_ylabel("Net return (%)", fontsize=8, color=INK2)
    handles, labels = axes[0].get_legend_handles_labels()
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    handles += [Patch(color=GRID, label="Random puts, 5th-95th pct"), Line2D([], [], color=MUTED, label="Random puts, mean")]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=7, frameon=False, bbox_to_anchor=(0.5, -0.07))
    fig.tight_layout()
    _save(fig, "fig2_period_returns_vs_random")


def figure_signal_test(sig: pd.DataFrame) -> None:
    allp = sig[sig["Period"] == "All (2021-2024)"].set_index("Group")
    groups = ["undervalued", "rich", "all"]
    names = {"undervalued": "Undervalued\n(signal)", "rich": "Rich", "all": "All near-ATM"}
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.7), sharey=True)
    for ax, h, title in zip(axes, ["t0_t1", "t1_t2"],
                            ["Signal close to next close", "Next close to following close\n(capturable after a next-bar fill)"]):
        for j, g in enumerate(groups):
            m, lo, hi = allp.loc[g, f"Hedged_{h}_Mean"], allp.loc[g, f"Hedged_{h}_CI_Lo"], allp.loc[g, f"Hedged_{h}_CI_Hi"]
            ax.bar(j, m, width=0.58, color=SERIES[j], edgecolor="white", linewidth=1)
            ax.errorbar(j, m, yerr=[[m - lo], [hi - m]], color=INK, capsize=3, linewidth=1)
            ax.text(j + 0.33, m, f"{m:+.1f}", va="center", ha="left", fontsize=7, color=INK)
        cost = allp.loc["undervalued", "Round_Trip_Cost_Mean"]
        ax.axhline(cost, color=INK2, linestyle="--", linewidth=0.9)
        ax.text(len(groups) - 0.45, cost, f"round-trip cost {cost:.1f}", va="bottom", ha="right", fontsize=7, color=INK2)
        ax.axhline(0, color=AXIS, linewidth=0.8)
        ax.set_xticks(range(len(groups)))
        ax.set_xticklabels([names[g] for g in groups], fontsize=7.5, color=INK2)
        ax.set_title(title, fontsize=8, color=INK)
        ax.spines[["top", "right"]].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(AXIS)
        ax.tick_params(colors=MUTED, labelcolor=INK2, labelsize=7.5)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Delta-hedged P&L per unit (INR)", fontsize=8, color=INK2)
    fig.tight_layout()
    _save(fig, "fig3_hedged_signal_test")


# ----------------------------------------------------------------------------- tables

def _ci(m: float, lo: float, hi: float, d: int = 1) -> str:
    if not np.isfinite(m):
        return "--"
    return f"{m:.{d}f} [{lo:.{d}f}, {hi:.{d}f}]"


def _num(v: float, d: int = 2, signed: bool = False) -> str:
    if v is None or not np.isfinite(v):
        return "--"
    return f"{v:+.{d}f}" if signed else f"{v:.{d}f}"


def _write_tex(name: str, header: List[str], rows: List[List[str]], colspec: str, caption: str, label: str,
               note: str = "", size: str = "\\small", wide: bool = False, midrules: List[int] = ()) -> None:
    """booktabs table; wide=True spans both IEEE columns. midrules: row indices to rule before."""
    env = "table*" if wide else "table"
    lines = [
        f"\\begin{{{env}}}[!t]", "\\centering", size, f"\\caption{{{caption}}}", f"\\label{{{label}}}",
        "\\resizebox{\\linewidth}{!}{%", f"\\begin{{tabular}}{{{colspec}}}", "\\toprule",
        " & ".join(header) + " \\\\", "\\midrule",
    ]
    for i, r in enumerate(rows):
        if i in midrules:
            lines.append("\\midrule")
        lines.append(" & ".join(r) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}}"]
    if note:
        lines += ["\\par\\vspace{2pt}", f"\\parbox{{\\linewidth}}{{\\footnotesize {note}}}"]
    lines += [f"\\end{{{env}}}", ""]
    with open(os.path.join(TABLES_DIR, f"{name}.tex"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def table_waterfall(wf: pd.DataFrame) -> None:
    rows = []
    for r in wf.itertuples():
        corr = r.Correction.replace("%", "\\%").replace(">=", "$\\geq$").replace("+ ", "")
        rows.append([r.Step, corr, str(r.Trades), _num(r.Return_Pct, 2, True), _num(r.Delta_Return_Pct, 2, True),
                     _ci(r.RoP_Mean_Pct, r.RoP_CI_Lo_Pct, r.RoP_CI_Hi_Pct), _num(r.Sharpe_Step_Legacy),
                     _num(r.Sharpe_MTM)])
    _write_tex(
        "tab_waterfall", ["Step", "Correction (cumulative)", "Trades", "Return \\%", "$\\Delta$", "Mean RoP \\% [95\\% CI]",
                          "Sharpe (step)", "Sharpe (MTM)"],
        rows, "llrrrlrr",
        "Correction waterfall on the original 180-session sample (Oct 2023 -- Jun 2024), Pure Mispricing strategy.",
        "tab:waterfall",
        "Each row adds one correction to all rows above it. Return is net P\\&L on INR 1 lakh. RoP is net return on "
        "premium per trade with a bootstrap 95\\% CI. Sharpe (step) is the original exit-only equity curve with a flat "
        "6.5\\% hurdle; Sharpe (MTM) uses daily contract-consistent marks and the RBI repo rate, and is shown only once "
        "positions are marked on their own contract.",
        size="\\scriptsize", wide=True,
    )


def table_periods(period_df: pd.DataFrame) -> None:
    rows = []
    for r in period_df.itertuples():
        rows.append([
            r.Period, r.Strategy.replace(" Mispricing", "").replace(" Filter", "").replace(" Baseline", ""),
            str(r.Trades), _num(r.Return_Pct, 1, True), _num(r.Return_Ex_Largest_Pct, 1, True),
            _ci(r.RoP_Mean_Pct, r.RoP_CI_Lo_Pct, r.RoP_CI_Hi_Pct), _num(r.RoP_Median_Pct, 1),
            _num(r.Win_Rate_Pct, 0), _num(r.Profit_Factor, 2), _num(r.Sharpe, 2), _num(r.Max_DD_Pct, 0),
            f"{r.Random_Mean_Return_Pct:+.1f} [{r.Random_P5_Return_Pct:+.0f}, {r.Random_P95_Return_Pct:+.0f}]",
            _num(r.Percentile_vs_Random, 0),
        ])
    _write_tex(
        "tab_period_results",
        ["Period", "Strategy", "N", "Ret \\%", "Ret ex-max \\%", "Mean RoP \\% [CI]", "Med RoP \\%", "Win \\%", "PF",
         "Sharpe", "MDD \\%", "Random puts \\% [5, 95]", "Pctl"],
        rows, "llrrrlrrrrrlr",
        "Corrected results, full-chain data, independent backtests from INR 1 lakh in each period.",
        "tab:periods",
        "Ret ex-max removes the single trade with the largest absolute P\\&L. RoP is net return on premium per trade "
        "(bootstrap 95\\% CI). PF is profit factor. Random puts: puts-only random entries on the signal expiry with the "
        "same fills, exits and costs, entry rate calibrated to the strategy's trade count; mean and 5th--95th "
        "percentiles over the draws. Pctl is the strategy's return percentile within that distribution.",
        size="\\scriptsize", wide=True, midrules=[3, 6, 9],
    )


def table_signal(sig: pd.DataFrame, label_suffix: str, caption: str) -> None:
    rows = []
    for r in sig.itertuples():
        if r.Group not in ("undervalued", "rich", "all"):
            continue
        rows.append([r.Period if r.Group == "undervalued" else "", r.Group.replace("_", " "), str(r.N),
                     _ci(r.Hedged_t0_t1_Mean, r.Hedged_t0_t1_CI_Lo, r.Hedged_t0_t1_CI_Hi, 2),
                     _ci(r.Hedged_t1_t2_Mean, r.Hedged_t1_t2_CI_Lo, r.Hedged_t1_t2_CI_Hi, 2),
                     _num(r.Excess_t1_t2_vs_All, 2, True) if r.Group != "all" else "", _num(r.Round_Trip_Cost_Mean, 2)])
    _write_tex(
        f"tab_signal_test_{label_suffix}",
        ["Period", "Group", "N", "$h_{t\\to t+1}$ [CI]", "$h_{t+1\\to t+2}$ [CI]", "Excess $h_{t+1\\to t+2}$", "Cost"],
        rows, "llrllrr", caption, f"tab:signal_{label_suffix}",
        "$h$ is the delta-hedged change in the put price per unit (INR): $\\Delta P - \\Delta_F\\,\\Delta F$ with the "
        "Black-76 forward delta at the surface IV and $F = S e^{rT}$ from the index close. Undervalued: put mispricing "
        "$< -\\epsilon_t$ (the entry signal); rich: $> +\\epsilon_t$. CIs are bootstrap 95\\% intervals clustered by "
        "date. Excess is the group mean minus the all-puts mean. Cost is the mean round-trip cost per unit.",
        size="\\scriptsize", wide=True, midrules=[3, 6, 9, 12],
    )


def table_breakdown(bd: pd.DataFrame) -> None:
    order = {"Pure Mispricing": 0, "Hybrid Filter": 1, "Retail Baseline": 2}
    bd = bd.sort_values(["Strategy", "Option_Type", "Exit_Signal"], key=lambda c: c.map(order) if c.name == "Strategy" else c)
    rows = [[r.Strategy.split()[0], r.Option_Type, r.Exit_Signal.replace("_", " ").lower(), str(r.Trades),
             f"{r.Net_PnL_INR:,.0f}", _num(r.RoP_Mean_Pct, 1, True), _num(r.Win_Rate_Pct, 0), _num(r.Mean_Holding_Bars, 1)]
            for r in bd.itertuples()]
    strategies = [r[0] for r in rows]
    breaks = [i for i in range(1, len(rows)) if strategies[i] != strategies[i - 1]]
    _write_tex(
        "tab_trade_breakdown", ["Strategy", "Type", "Exit", "N", "Net P\\&L (INR)", "Mean RoP \\%", "Win \\%", "Bars"],
        rows, "lllrrrrr",
        "Trades pooled over the four independent period runs, by option type and exit reason.", "tab:breakdown",
        size="\\scriptsize", midrules=breaks,
    )


def table_vix(vix: pd.DataFrame) -> None:
    rows = [[r.VIX_Regime.replace("<", "$<$").replace(">", "$>$"), r.Strategy.split()[0], str(r.Trades),
             _ci(r.RoP_Mean_Pct, r.RoP_CI_Lo_Pct, r.RoP_CI_Hi_Pct), _num(r.Win_Rate_Pct, 0)] for r in vix.itertuples()]
    _write_tex("tab_vix", ["India VIX at entry", "Strategy", "N", "Mean RoP \\% [CI]", "Win \\%"], rows, "llrlr",
               "Trade-level results by volatility regime, pooled over the independent period runs.", "tab:vix",
               size="\\scriptsize", midrules=[3, 6])


def table_stress(st: pd.DataFrame) -> None:
    rows = [[r.Multiplier, r.Protocol, str(r.Trades), _num(r.Return_A_Pct, 1, True), _num(r.Return_B_Pct, 1, True),
             _num(r.Return_C_Pct, 1, True), _num(r.Return_D_Pct, 1, True), _ci(r.RoP_Mean_Pct, r.RoP_CI_Lo_Pct, r.RoP_CI_Hi_Pct)]
            for r in st.itertuples()]
    _write_tex("tab_stress", ["Costs", "Entry threshold", "N", "A \\%", "B \\%", "C \\%", "D \\%", "Mean RoP \\% [CI]"],
               rows, "llrrrrrl", "Pure Mispricing under scaled transaction costs (independent period runs).", "tab:stress",
               "Epsilon fixed: realised costs scale, the entry threshold does not. Epsilon scaled: both scale.",
               size="\\scriptsize")


# ----------------------------------------------------------------------------- numbers

def write_numbers(p0: Dict, wf: pd.DataFrame, periods: pd.DataFrame, sig: pd.DataFrame, bd: pd.DataFrame,
                  extra: Dict) -> None:
    def cell(period: str, strat: str, col: str) -> float:
        return float(periods[(periods["Period"] == period) & (periods["Strategy"] == strat)][col].iloc[0])

    allsig = sig[sig["Period"] == "All (2021-2024)"].set_index("Group")
    w = wf.set_index("Step")
    n_positive = int((periods["Return_Pct"] > 0).sum())
    n_ci_above_zero = int((periods["RoP_CI_Lo_Pct"] > 0).sum())
    macros = {
        "HeadlineReturn": f"{w.loc['S0', 'Return_Pct']:.2f}",
        "HeadlineTrades": f"{int(w.loc['S0', 'Trades'])}",
        "HeadlineSharpe": f"{w.loc['S0', 'Sharpe_Step_Legacy']:.2f}",
        "ClosedFormReturn": f"{w.loc['S1', 'Return_Pct']:.2f}",
        "ForwardReturn": f"{w.loc['S2', 'Return_Pct']:.2f}",
        "ForwardTrades": f"{int(w.loc['S2', 'Trades'])}",
        "LagReturn": f"{w.loc['S3', 'Return_Pct']:.2f}",
        "LockReturn": f"{w.loc['S4', 'Return_Pct']:.2f}",
        "LockTrades": f"{int(w.loc['S4', 'Trades'])}",
        "FullChainDReturn": f"{w.loc['S6', 'Return_Pct']:.2f}",
        "FullChainDTrades": f"{int(w.loc['S6', 'Trades'])}",
        "GridErrMean": f"{p0['grid_error_call_mean']:.2f}",
        "GridErrMax": f"{p0['grid_error_call_max']:.2f}",
        "GridErrShare": f"{p0['grid_error_ge_half_eps_share_pct']:.1f}",
        "GridSpearman": f"{p0['corr_spearman_call']:.4f}",
        "ParityResidualMean": f"{p0['parity_residual_mean']:.2f}",
        "AtmPutBias": f"{p0['atm_put_mispricing_mean']:.2f}",
        "AtmCallBias": f"{p0['atm_call_mispricing_mean']:.2f}",
        "HeadlineSharpeMTM": f"{p0['pde_sharpe_mtm']:.2f}",
        "HeadlineMDDStep": f"{p0['pde_max_dd_step_pct']:.2f}",
        "HeadlineMDDMTM": f"{p0['pde_max_dd_mtm_pct']:.2f}",
        "PriceFieldMismatch": f"{p0['price_field_mismatch_all_pct']:.1f}",
        "PriceFieldMismatchTraded": f"{p0['price_field_mismatch_traded_pct']:.1f}",
        "CellsPositive": str(n_positive),
        "CellsCIAboveZero": str(n_ci_above_zero),
        "HybridAReturn": f"{cell('A (2021)', 'Hybrid Filter', 'Return_Pct'):.1f}",
        "HybridAExMax": f"{cell('A (2021)', 'Hybrid Filter', 'Return_Ex_Largest_Pct'):.1f}",
        "PureDReturn": f"{cell('D (Oct 2023-Jun 2024)', 'Pure Mispricing', 'Return_Pct'):.1f}",
        "PureDExMax": f"{cell('D (Oct 2023-Jun 2024)', 'Pure Mispricing', 'Return_Ex_Largest_Pct'):.1f}",
        "PureDLargest": f"{abs(cell('D (Oct 2023-Jun 2024)', 'Pure Mispricing', 'Largest_Trade_PnL')):,.0f}",
        "SigUnderHzeroMean": f"{allsig.loc['undervalued', 'Hedged_t0_t1_Mean']:.2f}",
        "SigRichHzeroMean": f"{allsig.loc['rich', 'Hedged_t0_t1_Mean']:.2f}",
        "SigAllHzeroMean": f"{allsig.loc['all', 'Hedged_t0_t1_Mean']:.2f}",
        "SigUnderHoneMean": f"{allsig.loc['undervalued', 'Hedged_t1_t2_Mean']:.2f}",
        "SigUnderHoneLo": f"{allsig.loc['undervalued', 'Hedged_t1_t2_CI_Lo']:.2f}",
        "SigUnderHoneHi": f"{allsig.loc['undervalued', 'Hedged_t1_t2_CI_Hi']:.2f}",
        "SigAllHoneMean": f"{allsig.loc['all', 'Hedged_t1_t2_Mean']:.2f}",
        "SigUnderHoneExcess": f"{allsig.loc['undervalued', 'Excess_t1_t2_vs_All']:.2f}",
        "SigUnderHzeroExcess": f"{allsig.loc['undervalued', 'Excess_t0_t1_vs_All']:.2f}",
        "SigRichHzeroExcess": f"{allsig.loc['rich', 'Excess_t0_t1_vs_All']:.2f}",
        "SigCost": f"{allsig.loc['undervalued', 'Round_Trip_Cost_Mean']:.2f}",
        "SigSpearman": f"{allsig.loc['all', 'Spearman_Mispricing_vs_t0_t1']:.2f}",
        "SigN": f"{int(allsig.loc['all', 'N']):,}",
        "SigNUnder": f"{int(allsig.loc['undervalued', 'N'])}",
        "PureTradesTotal": str(int(periods[periods["Strategy"] == "Pure Mispricing"]["Trades"].sum())),
        "PurePutsTotal": str(int(periods[periods["Strategy"] == "Pure Mispricing"]["Puts"].sum())),
        "HybridTradesTotal": str(int(periods[periods["Strategy"] == "Hybrid Filter"]["Trades"].sum())),
        "HybridPutsTotal": str(int(periods[periods["Strategy"] == "Hybrid Filter"]["Puts"].sum())),
        "PureStopLossPnL": f"{abs(bd[(bd['Strategy'] == 'Pure Mispricing') & (bd['Exit_Signal'] == 'STOP_LOSS')]['Net_PnL_INR'].sum()):,.0f}",
        "PureTakeProfitPnL": f"{bd[(bd['Strategy'] == 'Pure Mispricing') & (bd['Exit_Signal'] == 'TAKE_PROFIT')]['Net_PnL_INR'].sum():,.0f}",
        "RandomDraws": str(extra["random_draws"]),
        "LegacyCallMispricingMax": f"{extra['legacy_call_mispricing_max']:.4f}",
        "LegacyRolls": str(extra["legacy_rolls"]),
        "LegacyRollJumpMean": f"{extra['roll_jump_mean_pct']:.1f}",
        "LegacyRollJumpMedian": f"{extra['roll_jump_median_pct']:.1f}",
        "LegacyNonRollMean": f"{extra['nonroll_mean_pct']:.1f}",
        "PriceFieldWaterfallShare": f"{extra['price_field_share_pct']:.2f}",
    }
    with open(os.path.join(OUT_DIR, "numbers.tex"), "w", encoding="utf-8") as f:
        f.write("% Generated by research/reproduce_all.py -- do not edit by hand.\n")
        for k, v in macros.items():
            f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
    with open(os.path.join(OUT_DIR, "numbers.json"), "w", encoding="utf-8") as f:
        json.dump(macros, f, indent=2)


def legacy_panel_facts() -> Dict:
    """Facts about the legacy one-expiry 3.5-year panel quoted in the paper."""
    p = load_study_data(DATA_DIR, "legacy")["panel"]
    d = p.drop_duplicates("date")[["date", "expiry_date"]].sort_values("date").reset_index(drop=True)
    roll = d["expiry_date"] != d["expiry_date"].shift()
    roll_dates = set(d.loc[roll, "date"].iloc[1:])
    dates = d["date"].tolist()
    prev = dict(zip(dates[1:], dates[:-1]))
    px = {}
    for r in p.itertuples(index=False):
        px[(r.date, r.strike, "c")] = r.call_mkt_price
        px[(r.date, r.strike, "p")] = r.put_mkt_price
    rj, nj = [], []
    for (dt, k, t), v in px.items():
        a = px.get((prev.get(dt), k, t))
        if a and v and a > 5:
            (rj if dt in roll_dates else nj).append(v / a - 1)
    return {
        "legacy_call_mispricing_max": float(p["call_mispricing"].abs().max()),
        "legacy_rolls": int(roll.sum() - 1),
        "roll_jump_mean_pct": float(np.mean(rj) * 100), "roll_jump_median_pct": float(np.median(rj) * 100),
        "nonroll_mean_pct": float(np.mean(nj) * 100),
    }


def render(p0: Dict, wf_table: pd.DataFrame, period_df: pd.DataFrame, sig_tables: Dict[str, pd.DataFrame],
           breakdown: pd.DataFrame, vix: pd.DataFrame, stress: pd.DataFrame, extra: Dict) -> None:
    """Paper tables, figures and number macros from computed results."""
    table_waterfall(wf_table)
    table_periods(period_df)
    table_signal(sig_tables["v2"], "v2", "Delta-hedged next-bar P\\&L of the put signal, full-chain data (signal expiry $\\geq$ 14 DTE).")
    table_signal(sig_tables["legacy"], "legacy", "Delta-hedged next-bar P\\&L of the put signal, legacy one-expiry panel (nearest expiry $\\geq$ 7 DTE).")
    table_breakdown(breakdown)
    table_vix(vix)
    table_stress(stress)
    # Other research modules set a global plot style on import; start the figures from a clean state
    plt.style.use("default")
    plt.rcParams.update({"axes.grid": False, "font.family": "sans-serif"})
    figure_waterfall(wf_table)
    figure_period_vs_random(period_df)
    figure_signal_test(sig_tables["v2"])
    write_numbers(p0, wf_table, period_df, sig_tables["v2"], breakdown, extra)


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(TABLES_DIR, name))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--random-draws", type=int, default=500)
    parser.add_argument("--bhavcopy-dir", default=os.path.abspath(os.path.join(BASE_DIR, "..", "bhavcopy_cache")))
    parser.add_argument("--tables-only", action="store_true",
                        help="Rebuild LaTeX tables, figures and numbers from the saved CSVs (no backtests)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    os.makedirs(TABLES_DIR, exist_ok=True)
    os.makedirs(FIGURES_DIR, exist_ok=True)
    p0_path = os.path.join(BASE_DIR, "output", "phase0_diagnostics", "00_summary.json")
    extra_path = os.path.join(OUT_DIR, "extra.json")

    if args.tables_only:
        with open(p0_path, encoding="utf-8") as f:
            p0 = json.load(f)
        with open(extra_path, encoding="utf-8") as f:
            extra = json.load(f)
        render(p0, _read("waterfall_180d.csv"), _read("period_results.csv"),
               {"v2": _read("signal_test_v2.csv"), "legacy": _read("signal_test_legacy.csv")},
               _read("trade_breakdown.csv"), _read("vix_regime.csv"), _read("friction_stress.csv"), extra)
        logger.info(f"[SUCCESS] Tables, figures and numbers rebuilt in {OUT_DIR}")
        return

    started = datetime.now().isoformat(timespec="seconds")

    logger.info("[1/5] Phase 0 diagnostics (legacy 180-session sample)")
    run_phase0_diagnostics(bhavcopy_dir=args.bhavcopy_dir)
    with open(p0_path, encoding="utf-8") as f:
        p0 = json.load(f)

    logger.info("[2/5] Correction waterfall (180 sessions)")
    wf = run_waterfall(DATA_DIR)
    wf["table"].to_csv(os.path.join(TABLES_DIR, "waterfall_180d.csv"), index=False)

    logger.info("[3/5] 3.5-year independent period runs")
    res = run_master_3_5y_experiments(panel="v2", random_draws=args.random_draws)
    period_df = res["periods"]["table"]
    period_df.to_csv(os.path.join(TABLES_DIR, "period_results.csv"), index=False)
    res["breakdown"].to_csv(os.path.join(TABLES_DIR, "trade_breakdown.csv"), index=False)
    res["vix"].to_csv(os.path.join(TABLES_DIR, "vix_regime.csv"), index=False)
    res["stress"].to_csv(os.path.join(TABLES_DIR, "friction_stress.csv"), index=False)

    logger.info("[4/5] Delta-hedged signal test")
    sig_periods = {**SUB_PERIODS, "All (2021-2024)": (date(2021, 1, 1), date(2024, 6, 28))}
    sig_tables = {}
    for panel in ("v2", "legacy"):
        data = load_study_data(DATA_DIR, panel)
        obs = collect_signal_observations(data["panel"], data["marks"], data["ohlcv"])
        obs.to_csv(os.path.join(TABLES_DIR, f"signal_observations_{panel}.csv"), index=False)
        sig_tables[panel] = summarize_signal_test(obs, sig_periods)
        sig_tables[panel].to_csv(os.path.join(TABLES_DIR, f"signal_test_{panel}.csv"), index=False)

    logger.info("[5/5] Tables, figures, numbers, manifest")
    extra = {"random_draws": args.random_draws, **legacy_panel_facts(),
             "price_field_share_pct": 100 * max(wf["price_field"]["call_price_differs_share"], wf["price_field"]["put_price_differs_share"])}
    with open(extra_path, "w", encoding="utf-8") as f:
        json.dump(extra, f, indent=2)
    render(p0, wf["table"], period_df, sig_tables, res["breakdown"], res["vix"], res["stress"], extra)

    inputs = sorted(f for f in os.listdir(DATA_DIR) if f.endswith((".parquet", ".csv")))
    manifest = {
        "generated_at": started,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "command": " ".join([os.path.basename(sys.executable)] + sys.argv),
        "git_commit": _git("rev-parse", "HEAD"),
        # Uncommitted code changes (outputs excluded) mean the commit hash does not fully describe the run
        "git_dirty_code": bool(_git("status", "--porcelain", "--", "research", ":!research/output", ":!research/paper")),
        "python": platform.python_version(),
        "packages": {m: __import__(m).__version__ for m in ("numpy", "pandas", "scipy", "matplotlib", "pyarrow")},
        "config": CONFIG,
        "waterfall_bridge_check": wf["bridge"],
        "price_field_check": wf["price_field"],
        "bhavcopy_dir": os.path.relpath(args.bhavcopy_dir, os.path.join(BASE_DIR, "..")),
        "bhavcopy_files": len([f for f in os.listdir(args.bhavcopy_dir) if f.endswith(".parquet")]),
        "inputs_sha256": {f: _sha256(os.path.join(DATA_DIR, f)) for f in inputs},
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    logger.info(f"[SUCCESS] Outputs in {OUT_DIR}")


if __name__ == "__main__":
    main()

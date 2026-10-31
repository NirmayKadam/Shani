"""
Figures for the lab documents. Same validated palette and chart conventions as
research/reproduce_all.py (dataviz reference palette, light mode).
"""

import os
import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from lab_data import PAPER_OUT, PERIODS, STRATS, LabData

INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
PERIOD_SHORT = ["A (2021)", "B (2022)", "C (2023)", "D (2023-24)"]

def _reset_style():
    # research/analysis/plots.py applies a global seaborn style when the research code is
    # imported (the timing step does that); start every figure from a clean state.
    plt.style.use("default")
    plt.rcParams.update({"axes.grid": False, "font.family": "sans-serif", "font.size": 9})


def _axes(ax, grid_axis="y"):
    ax.spines[["top", "right"]].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelcolor=INK2, labelsize=8)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _save(fig, path):
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def copy_paper_figures(out_dir: str) -> dict:
    src = os.path.join(PAPER_OUT, "figures")
    names = {"waterfall": "fig1_correction_waterfall.png", "periods": "fig2_period_returns_vs_random.png",
             "signal": "fig3_hedged_signal_test.png"}
    out = {}
    for k, n in names.items():
        out[k] = shutil.copy2(os.path.join(src, n), os.path.join(out_dir, n))
    return out


def workflow(out_dir: str) -> str:
    _reset_style()
    steps = [
        ("1. Problem & literature", "Retail options losses;\nmodel-mispricing claims"),
        ("2. Data", "NSE Bhavcopy 2021-24\n(full option chain)"),
        ("3. Signal", "Black-76 forward, IV,\nspline surface, mispricing"),
        ("4. Strategies", "Pure, Hybrid, Retail,\nrandom-put baseline"),
        ("5. Backtest engine", "Next-bar fill, contract-locked\nmarks, Indian costs"),
        ("6. Evaluation", "Waterfall, independent periods,\nbootstrap CI, hedged test"),
        ("7. Results & paper", "Null result, reproducible\nmanifest, IEEE paper"),
    ]
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.set_xlim(0, 10); ax.set_ylim(0, 3.6); ax.axis("off")
    pos = [(0.15, 2.0), (2.65, 2.0), (5.15, 2.0), (7.65, 2.0), (7.65, 0.15), (5.15, 0.15), (2.65, 0.15)]
    w, h = 2.2, 1.35
    for i, ((title, body), (x, y)) in enumerate(zip(steps, pos)):
        face = "#eef4fc" if i < 6 else "#fdeee6"
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    linewidth=1.2, edgecolor=SERIES[0] if i < 6 else SERIES[1], facecolor=face))
        ax.text(x + w / 2, y + h - 0.32, title, ha="center", va="center", fontsize=9, fontweight="bold", color=INK)
        ax.text(x + w / 2, y + 0.5, body, ha="center", va="center", fontsize=7.6, color=INK2, linespacing=1.3)
    arrows = [((2.35, 2.67), (2.65, 2.67)), ((4.85, 2.67), (5.15, 2.67)), ((7.35, 2.67), (7.65, 2.67)),
              ((8.75, 2.0), (8.75, 1.5)), ((7.65, 0.82), (7.35, 0.82)), ((5.15, 0.82), (4.85, 0.82))]
    for a, b in arrows:
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, color=INK2, linewidth=1.2))
    ax.text(0.15, 0.82, "Corrections found in\nreview loop back to\nsteps 3-5 (Exp. 7)", fontsize=7.5,
            color=MUTED, va="center", style="italic")
    return _save(fig, os.path.join(out_dir, "exp2_workflow.png"))


def rop_ci_by_method(d: LabData, out_dir: str) -> str:
    _reset_style()
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    x = np.arange(len(PERIODS))
    for j, s in enumerate(STRATS):
        sub = d.periods[d.periods["Strategy"] == s].set_index("Period").loc[PERIODS]
        m, lo, hi = sub["RoP_Mean_Pct"].values, sub["RoP_CI_Lo_Pct"].values, sub["RoP_CI_Hi_Pct"].values
        xs = x + (j - 1) * 0.22
        ax.errorbar(xs, m, yerr=[m - lo, hi - m], fmt="o", color=SERIES[j], ecolor=SERIES[j], elinewidth=1.4,
                    capsize=3, markersize=6, markeredgecolor="white", label=s)
    ax.axhline(0, color=AXIS, linewidth=1)
    ax.set_xticks(x); ax.set_xticklabels(PERIOD_SHORT, fontsize=8, color=INK2)
    ax.set_ylabel("Mean net return per trade (% of premium)", fontsize=8, color=INK2)
    _axes(ax)
    ax.legend(fontsize=7.5, frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    return _save(fig, os.path.join(out_dir, "exp4_rop_ci_by_method.png"))


def returns_vs_method(d: LabData, out_dir: str) -> str:
    _reset_style()
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    x = np.arange(len(PERIODS))
    labels = STRATS + ["Random puts (mean)"]
    for j, lab in enumerate(labels):
        if j < 3:
            vals = d.periods[d.periods["Strategy"] == lab].set_index("Period").loc[PERIODS, "Return_Pct"].values
        else:
            vals = d.periods[d.periods["Strategy"] == "Pure Mispricing"].set_index("Period").loc[PERIODS, "Random_Mean_Return_Pct"].values
        ax.bar(x + (j - 1.5) * 0.2, vals, width=0.19, color=SERIES[j], edgecolor="white", linewidth=1, label=lab)
    ax.axhline(0, color=AXIS, linewidth=1)
    ax.set_xticks(x); ax.set_xticklabels(PERIOD_SHORT, fontsize=8, color=INK2)
    ax.set_ylabel("Net return on INR 1 lakh (%)", fontsize=8, color=INK2)
    _axes(ax)
    ax.legend(fontsize=7.5, frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    return _save(fig, os.path.join(out_dir, "exp4_return_vs_method.png"))


def rop_boxplot(d: LabData, out_dir: str) -> str:
    _reset_style()
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    data = [d.trades[d.trades["Strategy"] == s]["rop_pct"].values for s in STRATS]
    bp = ax.boxplot(data, vert=True, patch_artist=True, widths=0.5, showfliers=True,
                    medianprops={"color": INK, "linewidth": 1.4},
                    whiskerprops={"color": INK2}, capprops={"color": INK2},
                    flierprops={"marker": "o", "markersize": 3, "markerfacecolor": MUTED, "markeredgecolor": "none"})
    for patch, c in zip(bp["boxes"], SERIES):
        patch.set_facecolor(c); patch.set_alpha(0.85); patch.set_edgecolor("white")
    for j, v in enumerate(data):
        ax.scatter(j + 1, v.mean(), marker="D", s=26, color="white", edgecolor=INK, zorder=3)
    ax.axhline(0, color=AXIS, linewidth=1)
    ax.set_xticks([1, 2, 3]); ax.set_xticklabels([f"{s}\n(n={len(v)})" for s, v in zip(STRATS, data)], fontsize=8, color=INK2)
    ax.set_ylabel("Net return on premium per trade (%)", fontsize=8, color=INK2)
    ax.text(3.45, ax.get_ylim()[1] * 0.92, "◇ mean", fontsize=7.5, color=INK2, ha="right")
    _axes(ax)
    return _save(fig, os.path.join(out_dir, "exp5_rop_boxplot.png"))


def confusion_matrix(d: LabData, out_dir: str) -> str:
    _reset_style()
    cm = d.facts["confusion"]["t1_t2"]
    mat = np.array([[cm["tp"], cm["fn"]], [cm["fp"], cm["tn"]]])
    fig, ax = plt.subplots(figsize=(4.6, 3.8))
    norm = mat / mat.max()
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("seq", SEQ)
    ax.imshow(norm, cmap=cmap, vmin=0, vmax=1)
    labels = [["TP", "FN"], ["FP", "TN"]]
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{labels[i][j]}\n{mat[i, j]:,}", ha="center", va="center", fontsize=12,
                    color="white" if norm[i, j] > 0.5 else INK, fontweight="bold")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Signal: undervalued\n(predicted +)", "No signal\n(predicted −)"], fontsize=8, color=INK2)
    ax.set_yticks([0, 1]); ax.set_yticklabels(["Earned costs\n(actual +)", "Did not\n(actual −)"], fontsize=8, color=INK2)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    return _save(fig, os.path.join(out_dir, "exp5_confusion_matrix.png"))


def poster(d: LabData, figs: dict, out_dir: str) -> str:
    _reset_style()
    n = d.numbers
    fig = plt.figure(figsize=(16.5, 23.4))  # A2 portrait proportions
    fig.patch.set_facecolor("white")
    top = fig.add_axes([0, 0.9, 1, 0.1]); top.axis("off")
    top.add_patch(plt.Rectangle((0, 0), 1, 1, color="#0d366b", transform=top.transAxes))
    top.text(0.5, 0.64, "How an Apparent Options Alpha Disappears", color="white", fontsize=40, fontweight="bold",
             ha="center", va="center", transform=top.transAxes)
    top.text(0.5, 0.36, "A correction audit of a model-mispricing strategy on NIFTY 50 index options", color="#cde2fb",
             fontsize=22, ha="center", va="center", transform=top.transAxes)
    top.text(0.5, 0.12, "Hirdhay Jadhwani · Siddharth Jogi · Sumanyu Joshi · Nirmay Kadam   |   Dept. of Information Technology, VESIT",
             color="white", fontsize=15, ha="center", va="center", transform=top.transAxes)

    def block(rect, title, lines, size=15):
        ax = fig.add_axes(rect); ax.axis("off")
        ax.text(0, 1, title, fontsize=22, fontweight="bold", color="#0d366b", va="top", transform=ax.transAxes)
        ax.plot([0, 1], [0.93, 0.93], color=SERIES[0], linewidth=2, transform=ax.transAxes)
        y = 0.86
        for ln in lines:
            ax.text(0, y, ln, fontsize=size, color=INK, va="top", transform=ax.transAxes, wrap=True)
            y -= 0.115 if "\n" not in ln else 0.17

    block([0.04, 0.755, 0.43, 0.125], "Problem", [
        f"• An earlier draft reported +{n['HeadlineReturn']}% (Sharpe {n['HeadlineSharpe']})",
        "  from buying options below a Crank-Nicolson fair value.",
        "• Does that profit survive a correct backtest?",
        "• Does the mispricing signal carry any tradeable edge?",
    ])
    block([0.53, 0.755, 0.43, 0.125], "Data & method", [
        f"• {d.facts['sessions']} NSE sessions, Jan 2021 – Jun 2024",
        f"• {d.facts['full_chain_rows']:,} contract-days rebuilt from Bhavcopy",
        "• Next-bar fills, contract-locked marks, full Indian costs",
        "• Independent periods, bootstrap CIs, random baseline",
    ])

    def image(rect, path, title):
        ax = fig.add_axes(rect); ax.axis("off")
        ax.imshow(mpimg.imread(path))
        ax.set_title(title, fontsize=19, fontweight="bold", color="#0d366b", loc="left", pad=10)

    image([0.04, 0.52, 0.92, 0.215], figs["waterfall"], "1. The headline disappears one correction at a time")
    image([0.04, 0.275, 0.92, 0.215], figs["periods"], "2. Corrected 2021-24 results vs a matched random baseline")
    image([0.04, 0.06, 0.45, 0.18], figs["signal"], "3. The signal, delta-hedged")
    block([0.53, 0.06, 0.43, 0.18], "Findings", [
        f"• Closed-form pricing: +{n['ClosedFormReturn']}%; forward-",
        f"  consistent pricing: +{n['ForwardReturn']}% on {n['ForwardTrades']} trades",
        f"• {n['CellsPositive']} of 12 cells profitable; {n['CellsCIAboveZero']} with CI above 0",
        f"• Hedged excess after fill: INR {n['SigUnderHoneExcess']} vs cost {n['SigCost']}",
        "• Apparent alpha = pricing artifacts",
    ], size=14)
    foot = fig.add_axes([0, 0, 1, 0.035]); foot.axis("off")
    foot.text(0.5, 0.5, f"Code & data: tag paper-audit-v1 · every number regenerated by research/reproduce_all.py (commit {d.facts['commit']})",
              fontsize=13, color=INK2, ha="center", va="center")
    return _save(fig, os.path.join(out_dir, "exp10_poster.png"))

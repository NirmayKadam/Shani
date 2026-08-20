"""
File Overview: Publication-Ready Figure & Plot Generator for Quantitative Research Paper.
Generates academic quality charts (300 DPI PNG & vector PDF) with clean minimalist styling.
"""

import os
from typing import List, Dict, Any, Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

from research.backtest.engine import BacktestResult

# Set clean academic style
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "figure.titlesize": 13,
        "figure.dpi": 300,
    }
)

COLOR_BASELINE = "#D9534F"     # Red / Amber
COLOR_PDE = "#337AB7"          # Blue
COLOR_HYBRID = "#2E7D32"       # Dark Green


class FigureGenerator:
    """Generates and exports all manuscript charts and visual diagnostics."""

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = output_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "output", "figures")
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def plot_equity_curves(self, results: List[BacktestResult], filename_prefix: str = "fig1_equity_curves") -> str:
        """
        Figure 1: Cumulative Equity Curves for All 3 Strategies over time.
        """
        fig, ax = plt.subplots(figsize=(9, 4.8))

        colors = {"Retail_Baseline_RSI_MACD": COLOR_BASELINE, "Challenger_A_Pure_PDE": COLOR_PDE, "Challenger_B_Hybrid_QuantMental": COLOR_HYBRID}
        labels = {
            "Retail_Baseline_RSI_MACD": "Baseline (RSI + MACD)",
            "Challenger_A_Pure_PDE": "Challenger A (Crank-Nicolson PDE Mispricing)",
            "Challenger_B_Hybrid_QuantMental": "Challenger B (Hybrid Quant-Mental Filter)",
        }

        for r in results:
            df = r.equity_curve
            strat_color = colors.get(r.strategy_name, "#555555")
            strat_label = labels.get(r.strategy_name, r.strategy_name)
            ax.plot(df["date"], df["equity"], label=f"{strat_label} (Sharpe: {r.sharpe_ratio:.2f})", color=strat_color, linewidth=1.8)

        ax.axhline(100_000, color="#888888", linestyle="--", linewidth=1.0, alpha=0.7, label="Initial Capital (INR 100,000)")
        ax.set_title("Figure 1: Cumulative Equity Curves under Indian Statutory Frictions (NIFTY 50)", pad=12, fontweight="bold")
        ax.set_xlabel("Date")
        ax.set_ylabel("Portfolio Value (INR)")
        ax.legend(loc="upper left", frameon=True)
        fig.autofmt_xdate()
        fig.tight_layout()

        png_path = os.path.join(self.output_dir, f"{filename_prefix}.png")
        pdf_path = os.path.join(self.output_dir, f"{filename_prefix}.pdf")
        fig.savefig(png_path, dpi=300)
        fig.savefig(pdf_path)
        plt.close(fig)
        return png_path

    def plot_drawdown_profiles(self, results: List[BacktestResult], filename_prefix: str = "fig2_drawdown_profiles") -> str:
        """
        Figure 2: Percentage Drawdown Profiles over time.
        """
        fig, ax = plt.subplots(figsize=(9, 4.2))

        colors = {"Retail_Baseline_RSI_MACD": COLOR_BASELINE, "Challenger_A_Pure_PDE": COLOR_PDE, "Challenger_B_Hybrid_QuantMental": COLOR_HYBRID}
        labels = {
            "Retail_Baseline_RSI_MACD": "Baseline (RSI + MACD)",
            "Challenger_A_Pure_PDE": "Challenger A (PDE)",
            "Challenger_B_Hybrid_QuantMental": "Challenger B (Hybrid)",
        }

        for r in results:
            df = r.equity_curve
            equity = df["equity"].values
            running_max = np.maximum.accumulate(equity)
            dd = (equity - running_max) / np.maximum(running_max, 1.0) * 100.0

            strat_color = colors.get(r.strategy_name, "#555555")
            strat_label = labels.get(r.strategy_name, r.strategy_name)
            ax.plot(df["date"], dd, label=f"{strat_label} (Max DD: {r.max_drawdown_pct:.1f}%)", color=strat_color, linewidth=1.5)

        ax.set_title("Figure 2: Peak-to-Trough Drawdown Profiles (%)", pad=12, fontweight="bold")
        ax.set_xlabel("Date")
        ax.set_ylabel("Drawdown (%)")
        ax.axhline(0, color="#888888", linestyle="-", linewidth=0.8)
        ax.legend(loc="lower left", frameon=True)
        fig.autofmt_xdate()
        fig.tight_layout()

        png_path = os.path.join(self.output_dir, f"{filename_prefix}.png")
        pdf_path = os.path.join(self.output_dir, f"{filename_prefix}.pdf")
        fig.savefig(png_path, dpi=300)
        fig.savefig(pdf_path)
        plt.close(fig)
        return png_path

    def plot_mispricing_distribution(self, options_df: pd.DataFrame, filename_prefix: str = "fig3_mispricing_distribution") -> str:
        """
        Figure 3: Empirical Distribution of Crank-Nicolson PDE Mispricing (C_market - C_PDE).
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))

        call_mis = options_df["call_mispricing"].dropna().values
        put_mis = options_df["put_mispricing"].dropna().values

        # Call options mispricing histogram
        ax1.hist(call_mis, bins=40, color=COLOR_PDE, alpha=0.7, edgecolor="black", linewidth=0.5, density=True)
        ax1.axvline(0, color="red", linestyle="--", linewidth=1.2, label="Zero Mispricing")
        ax1.axvline(np.mean(call_mis), color="orange", linestyle="-", linewidth=1.2, label=f"Mean: INR {np.mean(call_mis):.2f}")
        ax1.set_title("Call Options Mispricing ($C_{mkt} - C_{PDE}$)")
        ax1.set_xlabel("Mispricing (INR)")
        ax1.set_ylabel("Probability Density")
        ax1.legend(loc="upper right")

        # Put options mispricing histogram
        ax2.hist(put_mis, bins=40, color=COLOR_HYBRID, alpha=0.7, edgecolor="black", linewidth=0.5, density=True)
        ax2.axvline(0, color="red", linestyle="--", linewidth=1.2, label="Zero Mispricing")
        ax2.axvline(np.mean(put_mis), color="orange", linestyle="-", linewidth=1.2, label=f"Mean: INR {np.mean(put_mis):.2f}")
        ax2.set_title("Put Options Mispricing ($P_{mkt} - P_{PDE}$)")
        ax2.set_xlabel("Mispricing (INR)")
        ax2.legend(loc="upper right")

        fig.suptitle("Figure 3: Empirical Distribution of Theoretical PDE Mispricing (NIFTY 50)", fontsize=12, fontweight="bold", y=1.02)
        fig.tight_layout()

        png_path = os.path.join(self.output_dir, f"{filename_prefix}.png")
        fig.savefig(png_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        return png_path

    def plot_friction_stress_test(self, stress_df: pd.DataFrame, filename_prefix: str = "fig4_friction_stress_test") -> str:
        """
        Figure 4: Sharpe Ratio Degradation across statutory cost multipliers.
        """
        fig, ax = plt.subplots(figsize=(8, 4.2))

        for strat_name, group in stress_df.groupby("Strategy"):
            label_map = {
                "Retail_Baseline_RSI_MACD": "Baseline (RSI + MACD)",
                "Challenger_A_Pure_PDE": "Challenger A (Pure PDE)",
                "Challenger_B_Hybrid_QuantMental": "Challenger B (Hybrid Filter)",
            }
            ax.plot(group["Friction_Multiplier"], group["Sharpe_Ratio"], marker="o", linewidth=1.8, label=label_map.get(strat_name, strat_name))

        ax.axhline(0, color="gray", linestyle="--", alpha=0.7)
        ax.set_title("Figure 4: Friction Sensitivity Analysis (Sharpe Ratio vs Statutory Friction Multiple)", pad=12, fontweight="bold")
        ax.set_xlabel("Friction Cost Multiplier")
        ax.set_ylabel("Annualized Sharpe Ratio")
        ax.legend(loc="upper right", frameon=True)
        fig.tight_layout()

        png_path = os.path.join(self.output_dir, f"{filename_prefix}.png")
        fig.savefig(png_path, dpi=300)
        plt.close(fig)
        return png_path

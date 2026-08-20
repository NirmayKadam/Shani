"""
File Overview: Quantitative Metrics Formatter and Tabulator for Research Papers.
Produces standardized Markdown and publication-ready LaTeX tables comparing strategy performance.
"""

from typing import List, Dict, Any
import pandas as pd
import numpy as np

from research.backtest.engine import BacktestResult


def generate_comparison_dataframe(results: List[BacktestResult]) -> pd.DataFrame:
    """
    Construct a clean pandas DataFrame summarizing all strategy results.
    """
    rows = []
    for r in results:
        rows.append(
            {
                "Strategy": r.strategy_name,
                "Total Return (%)": r.total_return_pct,
                "Sharpe Ratio": r.sharpe_ratio,
                "Sortino Ratio": r.sortino_ratio,
                "Max Drawdown (%)": r.max_drawdown_pct,
                "Profit Factor": r.profit_factor,
                "Win Rate (%)": r.win_rate,
                "Total Trades": r.total_trades,
                "Avg Win (INR)": r.avg_win,
                "Avg Loss (INR)": r.avg_loss,
                "Friction Paid (INR)": r.total_friction_paid,
                "Final Capital (INR)": r.final_capital,
            }
        )
    return pd.DataFrame(rows)


def to_latex_table(df: pd.DataFrame, caption: str = "Empirical Strategy Comparison", label: str = "tab:results") -> str:
    """
    Export DataFrame to formatted LaTeX table environment for academic paper.
    """
    return df.to_latex(
        index=False,
        caption=caption,
        label=label,
        float_format="%.2f",
        column_format="l" + "r" * (len(df.columns) - 1),
    )


def to_markdown_table(df: pd.DataFrame) -> str:
    """
    Export DataFrame to readable Markdown table string without external dependencies.
    """
    if df.empty:
        return ""

    headers = [str(c) for c in df.columns]
    lines = []
    # Header line
    lines.append("| " + " | ".join(headers) + " |")
    # Separator line
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    # Data rows
    for _, row in df.iterrows():
        row_str = []
        for val in row:
            if isinstance(val, (float, np.floating)):
                row_str.append(f"{val:.2f}")
            elif isinstance(val, (int, np.integer)):
                row_str.append(str(val))
            else:
                row_str.append(str(val))
        lines.append("| " + " | ".join(row_str) + " |")

    return "\n".join(lines)

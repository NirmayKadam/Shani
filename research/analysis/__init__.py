"""Research analysis package."""
from research.analysis.metrics import generate_comparison_dataframe, to_latex_table, to_markdown_table
from research.analysis.robustness import RobustnessAnalyzer
from research.analysis.plots import FigureGenerator

__all__ = [
    "generate_comparison_dataframe",
    "to_latex_table",
    "to_markdown_table",
    "RobustnessAnalyzer",
    "FigureGenerator",
]

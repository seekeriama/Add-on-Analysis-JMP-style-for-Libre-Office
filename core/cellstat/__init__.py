"""CellStat: statistical analysis for spreadsheets (MIT License)."""

from .api import ANALYSES, run, run_json
from .result import AnalysisError, Chart, Result, Table

__version__ = "0.1.0.dev0"
__all__ = ["ANALYSES", "run", "run_json", "AnalysisError", "Chart", "Result", "Table", "__version__"]

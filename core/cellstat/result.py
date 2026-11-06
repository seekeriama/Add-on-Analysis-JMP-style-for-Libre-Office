"""Result objects returned by every analysis.

A result is plain data: tables of values plus chart specifications. It never
touches a spreadsheet. Each host adapter (LibreOffice, Excel) turns a result
into its own cells and native charts, and the interactive panel turns the chart
specs into live plots.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


def clean(value: Any) -> Any:
    """Convert numpy scalars, NaN and infinities into JSON-friendly values."""
    if value is None:
        return None
    if hasattr(value, "item") and not isinstance(value, (list, tuple, dict)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, "tolist"):
        return clean(value.tolist())
    return value


@dataclass
class Table:
    """A titled grid of values with a header row."""

    title: str
    columns: list[str]
    rows: list[list[Any]]

    def to_dict(self) -> dict:
        return {"title": self.title, "columns": list(self.columns), "rows": clean(self.rows)}


@dataclass
class Chart:
    """A neutral chart description.

    ``kind`` is one of: histogram, box, scatter, line, bar, control, quantile.
    ``series`` is a list of dicts, each with a ``name`` and its data arrays
    (``x``/``y`` or ``values``), plus optional ``style`` hints such as
    ``"points"``, ``"line"`` or ``"step"``. ``ref_lines`` are horizontal or
    vertical reference lines (for example control limits).
    """

    kind: str
    title: str
    x_label: str = ""
    y_label: str = ""
    series: list[dict] = field(default_factory=list)
    ref_lines: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return clean(
            {
                "kind": self.kind,
                "title": self.title,
                "x_label": self.x_label,
                "y_label": self.y_label,
                "series": self.series,
                "ref_lines": self.ref_lines,
                **({"extra": self.extra} if self.extra else {}),
            }
        )


@dataclass
class Result:
    """Everything one analysis produces."""

    analysis: str
    title: str
    tables: list[Table] = field(default_factory=list)
    charts: list[Chart] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def table(self, title: str) -> Table:
        for t in self.tables:
            if t.title == title:
                return t
        raise KeyError(title)

    def value(self, table_title: str, row_label: str, column: str) -> Any:
        """Look up one cell by table title, first-column label and column name."""
        t = self.table(table_title)
        col = t.columns.index(column)
        for row in t.rows:
            if row[0] == row_label:
                return row[col]
        raise KeyError(row_label)

    def to_dict(self) -> dict:
        return {
            "analysis": self.analysis,
            "title": self.title,
            "tables": [t.to_dict() for t in self.tables],
            "charts": [c.to_dict() for c in self.charts],
            "notes": list(self.notes),
        }


class AnalysisError(ValueError):
    """Raised when the input data cannot be analysed; the message is shown to the user."""

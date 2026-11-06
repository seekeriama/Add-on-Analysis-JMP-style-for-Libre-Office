"""Turning raw spreadsheet cells into clean arrays."""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

import numpy as np

from .result import AnalysisError


def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def to_float(v: Any) -> float:
    """One cell to float; missing or non-numeric text becomes NaN."""
    if _is_missing(v):
        return math.nan
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    try:
        return float(str(v).strip().replace(",", ""))
    except ValueError:
        return math.nan


def to_label(v: Any) -> str | None:
    """One cell to a category label; missing becomes None.

    Whole numbers stored as floats (1.0) become "1" so numeric codes group
    the same way they look in the sheet.
    """
    if _is_missing(v):
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def numeric(values: Iterable[Any]) -> np.ndarray:
    return np.array([to_float(v) for v in values], dtype=float)


def labels(values: Iterable[Any]) -> list[str | None]:
    return [to_label(v) for v in values]


def is_numeric_column(values: Sequence[Any], threshold: float = 0.9) -> bool:
    """True when most non-missing cells parse as numbers."""
    present = [v for v in values if not _is_missing(v)]
    if not present:
        return False
    ok = sum(1 for v in present if not math.isnan(to_float(v)))
    return ok / len(present) >= threshold


def complete_rows(*columns: Sequence[Any], kinds: Sequence[str]) -> list[list[Any]]:
    """Keep rows where every column has a usable value.

    ``kinds`` gives "n" (numeric) or "c" (categorical) for each column.
    Returns the converted columns.
    """
    if len({len(c) for c in columns}) > 1:
        raise AnalysisError("All selected columns must have the same number of rows.")
    converted = []
    for col, kind in zip(columns, kinds):
        converted.append(numeric(col) if kind == "n" else labels(col))
    keep = []
    for i in range(len(columns[0]) if columns else 0):
        good = True
        for col, kind in zip(converted, kinds):
            v = col[i]
            if (kind == "n" and math.isnan(v)) or (kind == "c" and v is None):
                good = False
                break
        keep.append(good)
    out = []
    for col, kind in zip(converted, kinds):
        if kind == "n":
            out.append(np.asarray(col)[np.array(keep, dtype=bool)] if keep else np.array([]))
        else:
            out.append([v for v, k in zip(col, keep) if k])
    return out


def ordered_levels(values: Sequence[str]) -> list[str]:
    """Category levels sorted naturally: numbers numerically, then text."""

    def key(s: str):
        try:
            return (0, float(s), "")
        except ValueError:
            return (1, 0.0, s.lower())

    return sorted(set(values), key=key)

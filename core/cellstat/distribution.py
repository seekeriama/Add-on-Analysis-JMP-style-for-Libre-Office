"""Distribution of one numeric column."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from scipy import stats

from .data import complete_rows
from .result import AnalysisError, Chart, Result, Table

QUANTILE_LEVELS = [1.0, 0.995, 0.975, 0.90, 0.75, 0.50, 0.25, 0.10, 0.025, 0.005, 0.0]
QUANTILE_NAMES = {
    1.0: "100.0% maximum",
    0.995: "99.5%",
    0.975: "97.5%",
    0.90: "90.0%",
    0.75: "75.0% quartile",
    0.50: "50.0% median",
    0.25: "25.0% quartile",
    0.10: "10.0%",
    0.025: "2.5%",
    0.005: "0.5%",
    0.0: "0.0% minimum",
}


def box_stats(x: np.ndarray) -> dict:
    """Five-number summary plus 1.5 x IQR whiskers and outliers."""
    q1, med, q3 = np.quantile(x, [0.25, 0.5, 0.75])
    iqr = q3 - q1
    lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = x[(x >= lo_fence) & (x <= hi_fence)]
    return {
        "q1": q1,
        "median": med,
        "q3": q3,
        "whisker_low": inside.min() if inside.size else q1,
        "whisker_high": inside.max() if inside.size else q3,
        "outliers": sorted(x[(x < lo_fence) | (x > hi_fence)].tolist()),
        "mean": x.mean(),
    }


def histogram_bins(x: np.ndarray, bins: int | str = "auto") -> tuple[np.ndarray, np.ndarray]:
    counts, edges = np.histogram(x, bins=bins)
    return counts, edges


def normal_quantiles(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Sorted data against normal scores using Blom plotting positions."""
    xs = np.sort(x)
    n = xs.size
    p = (np.arange(1, n + 1) - 0.375) / (n + 0.25)
    return stats.norm.ppf(p), xs


def _anderson_darling(x: np.ndarray) -> float:
    xs = np.sort(x)
    n = xs.size
    z = stats.norm.cdf((xs - xs.mean()) / xs.std(ddof=1))
    z = np.clip(z, 1e-300, 1 - 1e-16)
    i = np.arange(1, n + 1)
    return float(-n - np.sum((2 * i - 1) * (np.log(z) + np.log(1 - z[::-1]))) / n)


def distribution(
    values: Sequence[Any],
    name: str = "Y",
    confidence: float = 0.95,
    bins: int | str = "auto",
) -> Result:
    (x,) = complete_rows(values, kinds="n")
    n = int(x.size)
    if n < 2:
        raise AnalysisError(f"{name}: need at least 2 numeric values, found {n}.")

    mean = float(x.mean())
    sd = float(x.std(ddof=1))
    se = sd / np.sqrt(n)
    tcrit = stats.t.ppf(0.5 + confidence / 2, n - 1)
    pct = f"{confidence * 100:g}%"

    moments = Table(
        "Summary statistics",
        ["Statistic", "Value"],
        [
            ["N", n],
            ["Mean", mean],
            ["Std dev", sd],
            ["Std error of mean", se],
            [f"Upper {pct} mean", mean + tcrit * se],
            [f"Lower {pct} mean", mean - tcrit * se],
            ["Variance", sd**2],
            ["Skewness", float(stats.skew(x, bias=False)) if n > 2 else None],
            ["Kurtosis (excess)", float(stats.kurtosis(x, bias=False)) if n > 3 else None],
            ["Coefficient of variation %", 100 * sd / mean if mean != 0 else None],
            ["Sum", float(x.sum())],
        ],
    )

    qs = np.quantile(x, QUANTILE_LEVELS)
    quantiles = Table(
        "Quantiles", ["Level", "Value"], [[QUANTILE_NAMES[q], float(v)] for q, v in zip(QUANTILE_LEVELS, qs)]
    )

    tests_rows = []
    if 3 <= n <= 5000:
        w, p = stats.shapiro(x)
        tests_rows.append(["Shapiro-Wilk", "W", float(w), float(p)])
    # Anderson-Darling with estimated mean and SD; Stephens' small-sample adjustment
    # and p-value approximation (D'Agostino & Stephens 1986, table 4.9).
    a2 = _anderson_darling(x) * (1 + 0.75 / n + 2.25 / n**2)
    if a2 >= 0.6:
        p_ad = np.exp(1.2937 - 5.709 * a2 + 0.0186 * a2**2)
    elif a2 >= 0.34:
        p_ad = np.exp(0.9177 - 4.279 * a2 - 1.38 * a2**2)
    elif a2 >= 0.2:
        p_ad = 1 - np.exp(-8.318 + 42.796 * a2 - 59.938 * a2**2)
    else:
        p_ad = 1 - np.exp(-13.436 + 101.14 * a2 - 223.73 * a2**2)
    tests_rows.append(["Anderson-Darling", "A²*", float(a2), float(min(max(p_ad, 0.0), 1.0))])
    normality = Table("Normality tests", ["Test", "Statistic name", "Statistic", "p-value"], tests_rows)

    counts, edges = histogram_bins(x, bins)
    box = box_stats(x)
    theo, xs = normal_quantiles(x)

    charts = [
        Chart(
            "histogram",
            f"Histogram of {name}",
            x_label=name,
            y_label="Count",
            series=[{"name": name, "edges": edges.tolist(), "counts": counts.tolist()}],
            extra={
                "normal_fit": {"mean": mean, "sd": sd},
            },
        ),
        Chart("box", f"Box plot of {name}", y_label=name, series=[{"name": name, **box}]),
        Chart(
            "quantile",
            f"Normal quantile plot of {name}",
            x_label="Normal quantile",
            y_label=name,
            series=[
                {"name": name, "x": theo.tolist(), "y": xs.tolist(), "style": "points"},
                {
                    "name": "Normal line",
                    "x": [float(theo[0]), float(theo[-1])],
                    "y": [mean + sd * float(theo[0]), mean + sd * float(theo[-1])],
                    "style": "line",
                },
            ],
        ),
    ]

    notes = []
    dropped = len(values) - n
    if dropped:
        notes.append(f"{dropped} missing or non-numeric cell(s) were ignored.")
    if n > 5000:
        notes.append("Shapiro-Wilk is skipped above 5000 rows; use Anderson-Darling.")

    return Result("distribution", f"Distribution of {name}", [moments, quantiles, normality], charts, notes)

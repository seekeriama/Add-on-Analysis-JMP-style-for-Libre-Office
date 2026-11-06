"""Process capability for a normally distributed measurement."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from scipy import stats

from .control import d2
from .data import complete_rows
from .result import AnalysisError, Chart, Result, Table


def capability(
    values: Sequence[Any],
    lsl: float | None = None,
    usl: float | None = None,
    target: float | None = None,
    subgroup: Sequence[Any] | None = None,
    subgroup_size: int | None = None,
    name: str = "Y",
    confidence: float = 0.95,
) -> Result:
    """Within (short-term) and overall (long-term) capability.

    Within sigma: R-bar/d2 for subgroups (or the moving range of 2 for
    individuals). Overall sigma: the sample standard deviation.
    """
    if lsl is None and usl is None:
        raise AnalysisError("Give at least one specification limit (LSL or USL).")
    if lsl is not None and usl is not None and lsl >= usl:
        raise AnalysisError("LSL must be below USL.")

    if subgroup is not None:
        x, sg = complete_rows(values, subgroup, kinds="nc")
        groups: dict[str, list[float]] = {}
        for v, g in zip(x, sg):
            groups.setdefault(g, []).append(v)
        arrs = [np.array(v) for v in groups.values() if len(v) >= 2]
        if not arrs:
            raise AnalysisError("Each subgroup needs at least 2 values.")
        sigma_within = float(np.mean([np.ptp(a) / d2(a.size) for a in arrs]))
        within_method = "Average subgroup range / d2"
    elif subgroup_size and subgroup_size >= 2:
        (x,) = complete_rows(values, kinds="n")
        k = x.size // subgroup_size
        if k < 2:
            raise AnalysisError("Need at least 2 full subgroups.")
        arrs = x[: k * subgroup_size].reshape(k, subgroup_size)
        sigma_within = float(np.ptp(arrs, axis=1).mean() / d2(subgroup_size))
        within_method = "Average subgroup range / d2"
    else:
        (x,) = complete_rows(values, kinds="n")
        if x.size < 3:
            raise AnalysisError("Need at least 3 values.")
        sigma_within = float(np.mean(np.abs(np.diff(x))) / d2(2))
        within_method = "Average moving range / d2"

    n = x.size
    mean = float(x.mean())
    sigma_overall = float(x.std(ddof=1))

    def indices(sigma):
        cp = (usl - lsl) / (6 * sigma) if lsl is not None and usl is not None else None
        cpl = (mean - lsl) / (3 * sigma) if lsl is not None else None
        cpu = (usl - mean) / (3 * sigma) if usl is not None else None
        cpk = min(v for v in (cpl, cpu) if v is not None)
        return cp, cpl, cpu, cpk

    cp, cpl, cpu, cpk = indices(sigma_within) if sigma_within > 0 else (None,) * 4
    pp, ppl, ppu, ppk = indices(sigma_overall) if sigma_overall > 0 else (None,) * 4

    # Confidence interval for Ppk (Bissell 1990) and Pp (chi-square).
    z = stats.norm.ppf(0.5 + confidence / 2)
    ppk_lo = ppk_hi = pp_lo = pp_hi = None
    if ppk is not None:
        half = z * np.sqrt(1 / (9 * n) + ppk**2 / (2 * (n - 1)))
        ppk_lo, ppk_hi = ppk - half, ppk + half
    if pp is not None:
        a = 1 - confidence
        pp_lo = pp * np.sqrt(stats.chi2.ppf(a / 2, n - 1) / (n - 1))
        pp_hi = pp * np.sqrt(stats.chi2.ppf(1 - a / 2, n - 1) / (n - 1))

    cpm = None
    if target is not None and lsl is not None and usl is not None:
        cpm = (usl - lsl) / (6 * np.sqrt(sigma_overall**2 + (mean - target) ** 2))

    pct = f"{confidence * 100:g}%"
    idx = Table(
        "Capability indices",
        ["Index", "Within", "Overall", f"Overall lower {pct}", f"Overall upper {pct}"],
        [
            ["Cp / Pp", cp, pp, pp_lo, pp_hi],
            ["CPL / PPL", cpl, ppl, None, None],
            ["CPU / PPU", cpu, ppu, None, None],
            ["Cpk / Ppk", cpk, ppk, ppk_lo, ppk_hi],
        ]
        + ([["Cpm", None, cpm, None, None]] if cpm is not None else []),
    )

    def ppm(sigma):
        below = stats.norm.cdf((lsl - mean) / sigma) * 1e6 if lsl is not None else 0.0
        above = stats.norm.sf((usl - mean) / sigma) * 1e6 if usl is not None else 0.0
        return below, above

    obs_below = float(np.mean(x < lsl) * 1e6) if lsl is not None else 0.0
    obs_above = float(np.mean(x > usl) * 1e6) if usl is not None else 0.0
    wb, wa = ppm(sigma_within) if sigma_within > 0 else (None, None)
    ob, oa = ppm(sigma_overall) if sigma_overall > 0 else (None, None)
    perf = Table(
        "Nonconforming parts per million",
        ["Region", "Observed", "Expected within", "Expected overall"],
        [
            ["Below LSL", obs_below if lsl is not None else None, wb if lsl is not None else None, ob if lsl is not None else None],
            ["Above USL", obs_above if usl is not None else None, wa if usl is not None else None, oa if usl is not None else None],
            ["Total", obs_below + obs_above, (wb or 0) + (wa or 0) if wb is not None else None, (ob or 0) + (oa or 0) if ob is not None else None],
        ],
    )
    summary = Table(
        "Process summary",
        ["Statistic", "Value"],
        [
            ["N", n],
            ["Mean", mean],
            ["Within sigma", sigma_within],
            ["Within sigma method", within_method],
            ["Overall sigma", sigma_overall],
            ["LSL", lsl],
            ["Target", target],
            ["USL", usl],
        ],
    )

    counts, edges = np.histogram(x, bins="auto")
    refs = []
    if lsl is not None:
        refs.append({"axis": "x", "value": lsl, "name": "LSL"})
    if target is not None:
        refs.append({"axis": "x", "value": target, "name": "Target"})
    if usl is not None:
        refs.append({"axis": "x", "value": usl, "name": "USL"})
    chart = Chart(
        "histogram",
        f"Capability of {name}",
        x_label=name,
        y_label="Count",
        series=[{"name": name, "edges": edges.tolist(), "counts": counts.tolist()}],
        ref_lines=refs,
        extra={
            "normal_fit": {"mean": mean, "sd": sigma_overall},
            "normal_fit_within": {"mean": mean, "sd": sigma_within},
        },
    )
    notes = []
    if 3 <= n <= 5000 and stats.shapiro(x).pvalue < 0.05:
        notes.append("Shapiro-Wilk rejects normality at 5%; normal-based indices may be misleading.")
    return Result("capability", f"Process capability of {name}", [summary, idx, perf], [chart], notes)

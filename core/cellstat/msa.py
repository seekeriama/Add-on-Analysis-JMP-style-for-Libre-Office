"""Measurement system analysis: crossed Gauge R&R by the ANOVA method (AIAG MSA, 4th ed.)."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from scipy import stats

from .data import complete_rows, ordered_levels
from .result import AnalysisError, Chart, Result, Table


def gauge_rr(
    measurement: Sequence[Any],
    part: Sequence[Any],
    operator: Sequence[Any],
    name: str = "Measurement",
    tolerance: float | None = None,
    study_multiplier: float = 6.0,
    alpha_interaction: float = 0.25,
) -> Result:
    """Crossed study: every operator measures every part the same number of times.

    The part-by-operator interaction is pooled into repeatability when its
    p-value exceeds ``alpha_interaction`` (AIAG default 0.25).
    """
    y, pg, og = complete_rows(measurement, part, operator, kinds="ncc")
    parts, ops = ordered_levels(pg), ordered_levels(og)
    p, o = len(parts), len(ops)
    if p < 2 or o < 2:
        raise AnalysisError("Need at least 2 parts and 2 operators.")
    pi = {v: i for i, v in enumerate(parts)}
    oi = {v: i for i, v in enumerate(ops)}
    cells: dict[tuple[int, int], list[float]] = {}
    for v, a, b in zip(y, pg, og):
        cells.setdefault((pi[a], oi[b]), []).append(v)
    sizes = {len(v) for v in cells.values()}
    if len(cells) != p * o or len(sizes) != 1:
        raise AnalysisError("The study must be balanced: every operator measures every part the same number of times.")
    r = sizes.pop()
    if r < 2:
        raise AnalysisError("Each operator must measure each part at least twice.")

    cube = np.zeros((p, o, r))
    for (i, j), v in cells.items():
        cube[i, j] = v
    grand = cube.mean()
    pm, om, cm = cube.mean(axis=(1, 2)), cube.mean(axis=(0, 2)), cube.mean(axis=2)
    ss_p = o * r * np.sum((pm - grand) ** 2)
    ss_o = p * r * np.sum((om - grand) ** 2)
    ss_po = r * np.sum((cm - pm[:, None] - om[None, :] + grand) ** 2)
    ss_e = np.sum((cube - cm[:, :, None]) ** 2)
    ss_t = np.sum((cube - grand) ** 2)
    df_p, df_o, df_po, df_e = p - 1, o - 1, (p - 1) * (o - 1), p * o * (r - 1)
    ms_p, ms_o, ms_po, ms_e = ss_p / df_p, ss_o / df_o, ss_po / df_po, ss_e / df_e
    f_po = ms_po / ms_e
    p_po = stats.f.sf(f_po, df_po, df_e)

    pooled = p_po > alpha_interaction
    if pooled:
        df_err = df_po + df_e
        ms_err = (ss_po + ss_e) / df_err
        f_p, f_o = ms_p / ms_err, ms_o / ms_err
        anova_rows = [
            ["Part", df_p, ss_p, ms_p, f_p, stats.f.sf(f_p, df_p, df_err)],
            ["Operator", df_o, ss_o, ms_o, f_o, stats.f.sf(f_o, df_o, df_err)],
            ["Repeatability (pooled)", df_err, ss_po + ss_e, ms_err, None, None],
            ["Total", p * o * r - 1, ss_t, None, None, None],
        ]
        var_e = ms_err
        var_po = 0.0
        var_o = max((ms_o - ms_err) / (p * r), 0.0)
        var_p = max((ms_p - ms_err) / (o * r), 0.0)
    else:
        f_p, f_o = ms_p / ms_po, ms_o / ms_po
        anova_rows = [
            ["Part", df_p, ss_p, ms_p, f_p, stats.f.sf(f_p, df_p, df_po)],
            ["Operator", df_o, ss_o, ms_o, f_o, stats.f.sf(f_o, df_o, df_po)],
            ["Part × Operator", df_po, ss_po, ms_po, f_po, p_po],
            ["Repeatability", df_e, ss_e, ms_e, None, None],
            ["Total", p * o * r - 1, ss_t, None, None, None],
        ]
        var_e = ms_e
        var_po = max((ms_po - ms_e) / r, 0.0)
        var_o = max((ms_o - ms_po) / (p * r), 0.0)
        var_p = max((ms_p - ms_po) / (o * r), 0.0)

    var_repro = var_o + var_po
    var_grr = var_e + var_repro
    var_total = var_grr + var_p
    comps = [
        ("Total Gauge R&R", var_grr),
        ("  Repeatability", var_e),
        ("  Reproducibility", var_repro),
        ("    Operator", var_o),
        ("    Part × Operator", var_po),
        ("Part-to-part", var_p),
        ("Total variation", var_total),
    ]
    k = study_multiplier
    sd_total = np.sqrt(var_total)
    rows = []
    for label, v in comps:
        sd = np.sqrt(v)
        row = [label, v, 100 * v / var_total if var_total > 0 else None, sd, k * sd,
               100 * sd / sd_total if sd_total > 0 else None]
        if tolerance:
            row.append(100 * k * sd / tolerance)
        rows.append(row)
    cols = ["Source", "Variance component", "% Contribution", "Std dev", f"Study var ({k:g} × SD)", "% Study var"]
    if tolerance:
        cols.append("% Tolerance")
    if pooled:  # the interaction was pooled into repeatability, so it has no row of its own
        rows = [row for row in rows if row[0].strip() != "Part × Operator"]
    var_table = Table("Variance components", cols, rows)

    pct_sv = 100 * np.sqrt(var_grr) / sd_total if sd_total > 0 else np.nan
    ndc = int(np.floor(np.sqrt(2) * np.sqrt(var_p) / np.sqrt(var_grr))) if var_grr > 0 else None
    if pct_sv < 10:
        verdict = "Acceptable (under 10% of study variation)"
    elif pct_sv <= 30:
        verdict = "Conditionally acceptable (10% to 30%); depends on the application and cost"
    else:
        verdict = "Not acceptable (over 30% of study variation)"
    summary = Table(
        "Summary",
        ["Statistic", "Value"],
        [
            ["Parts", p],
            ["Operators", o],
            ["Replicates", r],
            ["% Study var for Gauge R&R", pct_sv],
            ["Number of distinct categories", ndc],
            ["Interaction pooled into repeatability", "Yes" if pooled else "No"],
            ["Assessment (AIAG guideline)", verdict],
        ],
    )
    anova = Table("Two-way ANOVA", ["Source", "DF", "Sum of squares", "Mean square", "F ratio", "p-value"], anova_rows)

    # Charts: components bar, measurements by part for each operator, operator×part means.
    bar_labels = ["Gauge R&R", "Repeatability", "Reproducibility", "Part-to-part"]
    vals = [var_grr, var_e, var_repro, var_p]
    charts = [
        Chart(
            "bar",
            "Components of variation",
            x_label="Component",
            y_label="Percent",
            series=[
                {"name": "% Contribution", "x": bar_labels, "y": [100 * v / var_total for v in vals]},
                {"name": "% Study var", "x": bar_labels, "y": [100 * np.sqrt(v) / sd_total for v in vals]},
            ],
        ),
        Chart(
            "line",
            "Part × operator interaction",
            x_label="Part",
            y_label=f"Mean {name}",
            series=[{"name": op, "x": parts, "y": cm[:, j].tolist(), "style": "points-line"} for j, op in enumerate(ops)],
            extra={"x_categorical": True},
        ),
        Chart(
            "box",
            f"{name} by operator",
            x_label="Operator",
            y_label=name,
            series=[{"name": op, **_box(cube[:, j, :].ravel())} for j, op in enumerate(ops)],
        ),
    ]
    return Result("gauge_rr", f"Gauge R&R (ANOVA method) of {name}", [summary, var_table, anova], charts)


def _box(v):
    from .distribution import box_stats

    return box_stats(v)

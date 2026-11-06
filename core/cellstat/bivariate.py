"""Fit Y by X: picks the analysis from the column types.

=============  ==============  ===========================================
Y              X               Analysis
=============  ==============  ===========================================
numeric        numeric         Simple linear regression (bivariate fit)
numeric        categorical     One-way ANOVA with Tukey HSD
categorical    categorical     Contingency table with chi-square tests
categorical    numeric         Not yet supported (logistic regression)
=============  ==============  ===========================================
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from scipy import stats

from .data import complete_rows, is_numeric_column, ordered_levels
from .result import AnalysisError, Chart, Result, Table


def fit_y_by_x(
    y: Sequence[Any],
    x: Sequence[Any],
    y_name: str = "Y",
    x_name: str = "X",
    y_type: str | None = None,
    x_type: str | None = None,
    confidence: float = 0.95,
) -> Result:
    """``y_type``/``x_type`` are "continuous" or "nominal"; detected when None."""
    yt = y_type or ("continuous" if is_numeric_column(y) else "nominal")
    xt = x_type or ("continuous" if is_numeric_column(x) else "nominal")
    if yt == "continuous" and xt == "continuous":
        return bivariate_fit(y, x, y_name, x_name, confidence)
    if yt == "continuous" and xt == "nominal":
        return oneway(y, x, y_name, x_name, confidence)
    if yt == "nominal" and xt == "nominal":
        return contingency(y, x, y_name, x_name)
    raise AnalysisError(
        "A categorical Y with a numeric X needs logistic regression, which is not supported yet. "
        "Set X to categorical, or swap Y and X."
    )


# --------------------------------------------------------------------------- numeric by numeric


def bivariate_fit(y, x, y_name="Y", x_name="X", confidence=0.95) -> Result:
    yv, xv = complete_rows(y, x, kinds="nn")
    n = yv.size
    if n < 3:
        raise AnalysisError("Need at least 3 complete (X, Y) pairs for a line fit.")
    if np.ptp(xv) == 0:
        raise AnalysisError(f"{x_name} has the same value in every row; a line cannot be fitted.")

    xm, ym = xv.mean(), yv.mean()
    sxx = np.sum((xv - xm) ** 2)
    sxy = np.sum((xv - xm) * (yv - ym))
    slope = sxy / sxx
    intercept = ym - slope * xm
    fitted = intercept + slope * xv
    resid = yv - fitted
    dfe = n - 2
    sse = float(np.sum(resid**2))
    sst = float(np.sum((yv - ym) ** 2))
    ssm = sst - sse
    mse = sse / dfe
    rmse = np.sqrt(mse)
    r2 = ssm / sst if sst > 0 else np.nan
    adj_r2 = 1 - (1 - r2) * (n - 1) / dfe if sst > 0 else np.nan
    se_slope = rmse / np.sqrt(sxx)
    se_int = rmse * np.sqrt(1 / n + xm**2 / sxx)
    tcrit = stats.t.ppf(0.5 + confidence / 2, dfe)
    f = ssm / mse if mse > 0 else np.inf
    pf = stats.f.sf(f, 1, dfe)
    r = np.corrcoef(xv, yv)[0, 1]

    def est_row(term, b, se):
        t = b / se if se > 0 else np.inf
        return [term, b, se, t, 2 * stats.t.sf(abs(t), dfe), b - tcrit * se, b + tcrit * se]

    pct = f"{confidence * 100:g}%"
    estimates = Table(
        "Parameter estimates",
        ["Term", "Estimate", "Std error", "t ratio", "p-value", f"Lower {pct}", f"Upper {pct}"],
        [est_row("Intercept", intercept, se_int), est_row(x_name, slope, se_slope)],
    )
    summary = Table(
        "Summary of fit",
        ["Statistic", "Value"],
        [
            ["R²", r2],
            ["Adjusted R²", adj_r2],
            ["Root mean square error", rmse],
            ["Correlation r", r],
            [f"Mean of {y_name}", ym],
            ["Observations", n],
        ],
    )
    anova = Table(
        "Analysis of variance",
        ["Source", "DF", "Sum of squares", "Mean square", "F ratio", "p-value"],
        [
            ["Model", 1, ssm, ssm, f, pf],
            ["Error", dfe, sse, mse, None, None],
            ["Total", n - 1, sst, None, None, None],
        ],
    )

    # Confidence band for the fitted mean on a grid.
    grid = np.linspace(xv.min(), xv.max(), 50)
    gfit = intercept + slope * grid
    half = tcrit * rmse * np.sqrt(1 / n + (grid - xm) ** 2 / sxx)
    charts = [
        Chart(
            "scatter",
            f"{y_name} by {x_name}",
            x_label=x_name,
            y_label=y_name,
            series=[
                {"name": "Data", "x": xv.tolist(), "y": yv.tolist(), "style": "points"},
                {"name": "Linear fit", "x": grid.tolist(), "y": gfit.tolist(), "style": "line"},
                {"name": f"{pct} CI lower", "x": grid.tolist(), "y": (gfit - half).tolist(), "style": "dash"},
                {"name": f"{pct} CI upper", "x": grid.tolist(), "y": (gfit + half).tolist(), "style": "dash"},
            ],
            extra={"equation": f"{y_name} = {intercept:.6g} + {slope:.6g}·{x_name}"},
        ),
        Chart(
            "scatter",
            "Residuals by predicted",
            x_label=f"Predicted {y_name}",
            y_label="Residual",
            series=[{"name": "Residual", "x": fitted.tolist(), "y": resid.tolist(), "style": "points"}],
            ref_lines=[{"axis": "y", "value": 0, "name": "Zero"}],
        ),
    ]
    res = Result("bivariate", f"Bivariate fit of {y_name} by {x_name}", [summary, estimates, anova], charts)
    res.notes.append(f"Fitted line: {y_name} = {intercept:.6g} + {slope:.6g} × {x_name}")
    return res


# --------------------------------------------------------------------------- numeric by category


def oneway(y, x, y_name="Y", x_name="X", confidence=0.95) -> Result:
    yv, xg = complete_rows(y, x, kinds="nc")
    levels = ordered_levels(xg)
    if len(levels) < 2:
        raise AnalysisError(f"{x_name} needs at least 2 groups; found {len(levels)}.")
    xg_arr = np.array(xg, dtype=object)
    groups = [yv[xg_arr == lv] for lv in levels]
    if any(g.size == 0 for g in groups):
        raise AnalysisError("Every group needs at least one value.")
    n = yv.size
    k = len(levels)
    dfe = n - k
    if dfe < 1:
        raise AnalysisError("Need more observations than groups for a one-way ANOVA.")

    grand = yv.mean()
    ssb = float(sum(g.size * (g.mean() - grand) ** 2 for g in groups))
    sse = float(sum(np.sum((g - g.mean()) ** 2) for g in groups))
    sst = ssb + sse
    msb = ssb / (k - 1)
    mse = sse / dfe
    f = msb / mse if mse > 0 else np.inf
    p = stats.f.sf(f, k - 1, dfe)
    rmse = np.sqrt(mse)
    tcrit = stats.t.ppf(0.5 + confidence / 2, dfe)
    pct = f"{confidence * 100:g}%"

    anova = Table(
        "Analysis of variance",
        ["Source", "DF", "Sum of squares", "Mean square", "F ratio", "p-value"],
        [
            [x_name, k - 1, ssb, msb, f, p],
            ["Error", dfe, sse, mse, None, None],
            ["Total", n - 1, sst, None, None, None],
        ],
    )
    summary = Table(
        "Summary of fit",
        ["Statistic", "Value"],
        [
            ["R²", ssb / sst if sst > 0 else None],
            ["Adjusted R²", 1 - mse / (sst / (n - 1)) if sst > 0 else None],
            ["Root mean square error", rmse],
            [f"Mean of {y_name}", grand],
            ["Observations", n],
        ],
    )
    means_rows = []
    for lv, g in zip(levels, groups):
        se_pooled = rmse / np.sqrt(g.size)
        means_rows.append(
            [
                lv,
                int(g.size),
                g.mean(),
                g.std(ddof=1) if g.size > 1 else None,
                se_pooled,
                g.mean() - tcrit * se_pooled,
                g.mean() + tcrit * se_pooled,
            ]
        )
    means = Table(
        "Means",
        ["Level", "N", "Mean", "Std dev", "Std error (pooled)", f"Lower {pct}", f"Upper {pct}"],
        means_rows,
    )

    # Tukey-Kramer HSD on every pair.
    alpha = 1 - confidence
    qcrit = stats.studentized_range.ppf(confidence, k, dfe)
    tukey_rows = []
    for i in range(k):
        for j in range(i + 1, k):
            gi, gj = groups[i], groups[j]
            diff = gj.mean() - gi.mean()
            se = np.sqrt(mse / 2 * (1 / gi.size + 1 / gj.size))
            q = abs(diff) / se
            padj = stats.studentized_range.sf(q, k, dfe)
            tukey_rows.append(
                [f"{levels[j]} - {levels[i]}", diff, se * np.sqrt(2), diff - qcrit * se, diff + qcrit * se, padj]
            )
    tukey = Table(
        "Tukey HSD comparisons",
        ["Pair", "Difference", "Std error of difference", f"Lower {pct}", f"Upper {pct}", "Adjusted p-value"],
        tukey_rows,
    )

    lev_stat, lev_p = stats.levene(*groups, center="median") if all(g.size > 1 for g in groups) else (np.nan, np.nan)
    bart = stats.bartlett(*groups) if all(g.size > 1 for g in groups) else (np.nan, np.nan)
    welch = _welch_anova(groups)
    variance = Table(
        "Tests that the variances are equal",
        ["Test", "Statistic", "p-value"],
        [["Levene (Brown-Forsythe, median)", lev_stat, lev_p], ["Bartlett", bart[0], bart[1]]],
    )
    welch_t = Table(
        "Welch ANOVA (unequal variances)",
        ["Statistic", "Num DF", "Den DF", "p-value"],
        [[welch[0], welch[1], welch[2], welch[3]]],
    )

    point_x, point_y = [], []
    for lv, g in zip(levels, groups):
        point_x += [lv] * g.size
        point_y += g.tolist()
    charts = [
        Chart(
            "scatter",
            f"{y_name} by {x_name}",
            x_label=x_name,
            y_label=y_name,
            series=[
                {"name": "Data", "x": point_x, "y": point_y, "style": "points"},
                {"name": "Group mean", "x": levels, "y": [g.mean() for g in groups], "style": "mean-marker"},
                {
                    "name": f"{pct} CI",
                    "x": levels,
                    "low": [r[5] for r in means_rows],
                    "high": [r[6] for r in means_rows],
                    "style": "error-bar",
                },
            ],
            ref_lines=[{"axis": "y", "value": grand, "name": "Mean"}],
            extra={"x_categorical": True},
        ),
        Chart(
            "box",
            f"{y_name} by {x_name} (box plots)",
            x_label=x_name,
            y_label=y_name,
            series=[{"name": lv, **_box(g)} for lv, g in zip(levels, groups)],
        ),
    ]
    return Result(
        "oneway",
        f"One-way analysis of {y_name} by {x_name}",
        [summary, anova, means, tukey, variance, welch_t],
        charts,
    )


def _box(g):
    from .distribution import box_stats

    return box_stats(g)


def _welch_anova(groups):
    k = len(groups)
    if any(g.size < 2 for g in groups):
        return (np.nan, np.nan, np.nan, np.nan)
    ns = np.array([g.size for g in groups], dtype=float)
    ms = np.array([g.mean() for g in groups])
    vs = np.array([g.var(ddof=1) for g in groups])
    if np.any(vs == 0):
        return (np.nan, np.nan, np.nan, np.nan)
    w = ns / vs
    mw = np.sum(w * ms) / np.sum(w)
    a = np.sum(w * (ms - mw) ** 2) / (k - 1)
    lam = np.sum((1 - w / np.sum(w)) ** 2 / (ns - 1))
    b = 1 + 2 * (k - 2) / (k**2 - 1) * lam
    f = a / b
    df2 = (k**2 - 1) / (3 * lam)
    return (f, k - 1, df2, stats.f.sf(f, k - 1, df2))


# --------------------------------------------------------------------------- category by category


def contingency(y, x, y_name="Y", x_name="X") -> Result:
    yg, xg = complete_rows(y, x, kinds="cc")
    ylev, xlev = ordered_levels(yg), ordered_levels(xg)
    if len(ylev) < 2 or len(xlev) < 2:
        raise AnalysisError("Both columns need at least 2 categories for a contingency table.")
    yi = {v: i for i, v in enumerate(ylev)}
    xi = {v: i for i, v in enumerate(xlev)}
    counts = np.zeros((len(xlev), len(ylev)), dtype=int)
    for a, b in zip(xg, yg):
        counts[xi[a], yi[b]] += 1
    n = counts.sum()

    rows = []
    for i, lv in enumerate(xlev):
        rows.append([lv, *counts[i].tolist(), int(counts[i].sum())])
    rows.append(["Total", *counts.sum(axis=0).tolist(), int(n)])
    table = Table(f"Counts: {x_name} (rows) by {y_name} (columns)", [x_name, *ylev, "Total"], rows)

    row_pct = counts / counts.sum(axis=1, keepdims=True) * 100
    pct_table = Table(
        "Row percentages",
        [x_name, *ylev],
        [[lv, *row_pct[i].tolist()] for i, lv in enumerate(xlev)],
    )

    chi2, p, dof, expected = stats.chi2_contingency(counts, correction=False)
    g2, pg, _, _ = stats.chi2_contingency(counts, correction=False, lambda_="log-likelihood")
    test_rows = [["Pearson chi-square", chi2, dof, p], ["Likelihood ratio chi-square", g2, dof, pg]]
    if counts.shape == (2, 2):
        _, pf = stats.fisher_exact(counts)
        test_rows.append(["Fisher's exact (two-sided)", None, None, pf])
    tests = Table("Tests", ["Test", "Statistic", "DF", "p-value"], test_rows)

    notes = []
    if (expected < 5).mean() > 0.2:
        notes.append("More than 20% of expected counts are below 5; chi-square p-values may be unreliable.")

    chart = Chart(
        "bar",
        f"{y_name} by {x_name} (row %)",
        x_label=x_name,
        y_label="Percent",
        series=[{"name": lv, "x": xlev, "y": row_pct[:, j].tolist()} for j, lv in enumerate(ylev)],
        extra={"stacked": True},
    )
    return Result(
        "contingency", f"Contingency analysis of {y_name} by {x_name}", [table, pct_table, tests], [chart], notes
    )

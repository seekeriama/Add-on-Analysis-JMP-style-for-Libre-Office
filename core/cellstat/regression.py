"""Fit model: multiple least-squares regression with numeric and categorical terms."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
from scipy import stats

from .data import complete_rows, is_numeric_column, ordered_levels
from .result import AnalysisError, Chart, Result, Table


def fit_model(
    y: Sequence[Any],
    xs: Mapping[str, Sequence[Any]],
    y_name: str = "Y",
    x_types: Mapping[str, str] | None = None,
    confidence: float = 0.95,
) -> Result:
    """Ordinary least squares of ``y`` on the columns in ``xs``.

    Categorical terms use effect coding (sum-to-zero), so each estimate is a
    level's difference from the average of all levels; the last level's effect
    is minus the sum of the others. Effect tests are type III partial F tests.
    """
    if not xs:
        raise AnalysisError("Choose at least one X column.")
    x_types = dict(x_types or {})
    names = list(xs)
    kinds = []
    for nm in names:
        t = x_types.get(nm) or ("continuous" if is_numeric_column(xs[nm]) else "nominal")
        x_types[nm] = t
        kinds.append("n" if t == "continuous" else "c")
    cols = complete_rows(y, *[xs[nm] for nm in names], kinds="n" + "".join(kinds))
    yv = cols[0]
    n = yv.size

    design = [np.ones(n)]
    labels = ["Intercept"]
    term_cols: dict[str, list[int]] = {}
    for nm, kind, col in zip(names, kinds, cols[1:]):
        start = len(design)
        if kind == "n":
            design.append(np.asarray(col, dtype=float))
            labels.append(nm)
        else:
            levels = ordered_levels(col)
            if len(levels) < 2:
                raise AnalysisError(f"{nm} has only one category among the complete rows.")
            arr = np.array(col, dtype=object)
            last = levels[-1]
            for lv in levels[:-1]:
                design.append((arr == lv).astype(float) - (arr == last).astype(float))
                labels.append(f"{nm}[{lv}]")
        term_cols[nm] = list(range(start, len(design)))
    X = np.column_stack(design)
    p = X.shape[1]
    if n <= p:
        raise AnalysisError(f"Need more complete rows ({n}) than model parameters ({p}).")
    rank = np.linalg.matrix_rank(X)
    if rank < p:
        raise AnalysisError("Some X columns are exact linear combinations of others; remove one and refit.")

    beta, sse_full, ymean, sst, dfe, mse, xtx_inv = _ols(X, yv)
    rmse = np.sqrt(mse)
    se = np.sqrt(np.diag(xtx_inv) * mse)
    tvals = beta / se
    pvals = 2 * stats.t.sf(np.abs(tvals), dfe)
    tcrit = stats.t.ppf(0.5 + confidence / 2, dfe)
    pct = f"{confidence * 100:g}%"
    vif = _vif(X)

    est_rows = []
    for i, lab in enumerate(labels):
        est_rows.append(
            [lab, beta[i], se[i], tvals[i], pvals[i], beta[i] - tcrit * se[i], beta[i] + tcrit * se[i], vif[i]]
        )
    estimates = Table(
        "Parameter estimates",
        ["Term", "Estimate", "Std error", "t ratio", "p-value", f"Lower {pct}", f"Upper {pct}", "VIF"],
        est_rows,
    )

    ssm = sst - sse_full
    dfm = p - 1
    msm = ssm / dfm
    f = msm / mse if mse > 0 else np.inf
    anova = Table(
        "Analysis of variance",
        ["Source", "DF", "Sum of squares", "Mean square", "F ratio", "p-value"],
        [
            ["Model", dfm, ssm, msm, f, stats.f.sf(f, dfm, dfe)],
            ["Error", dfe, sse_full, mse, None, None],
            ["Total", n - 1, sst, None, None, None],
        ],
    )
    r2 = ssm / sst if sst > 0 else np.nan
    summary = Table(
        "Summary of fit",
        ["Statistic", "Value"],
        [
            ["R²", r2],
            ["Adjusted R²", 1 - (1 - r2) * (n - 1) / dfe],
            ["Root mean square error", rmse],
            [f"Mean of {y_name}", ymean],
            ["Observations", n],
        ],
    )

    effect_rows = []
    for nm in names:
        idx = term_cols[nm]
        keep = [i for i in range(p) if i not in idx]
        _, sse_red, *_ = _ols(X[:, keep], yv)
        ss = sse_red - sse_full
        df = len(idx)
        fe = (ss / df) / mse
        effect_rows.append([nm, df, ss, fe, stats.f.sf(fe, df, dfe)])
    effects = Table("Effect tests", ["Source", "DF", "Sum of squares", "F ratio", "p-value"], effect_rows)

    fitted = X @ beta
    resid = yv - fitted
    lo, hi = float(min(fitted.min(), yv.min())), float(max(fitted.max(), yv.max()))
    charts = [
        Chart(
            "scatter",
            f"Actual by predicted {y_name}",
            x_label=f"Predicted {y_name}",
            y_label=f"Actual {y_name}",
            series=[
                {"name": "Data", "x": fitted.tolist(), "y": yv.tolist(), "style": "points"},
                {"name": "Actual = predicted", "x": [lo, hi], "y": [lo, hi], "style": "line"},
            ],
        ),
        Chart(
            "scatter",
            "Residuals by predicted",
            x_label=f"Predicted {y_name}",
            y_label="Residual",
            series=[{"name": "Residual", "x": fitted.tolist(), "y": resid.tolist(), "style": "points"}],
            ref_lines=[{"axis": "y", "value": 0, "name": "Zero"}],
        ),
        Chart(
            "line",
            "Residuals by row",
            x_label="Row",
            y_label="Residual",
            series=[{"name": "Residual", "x": list(range(1, n + 1)), "y": resid.tolist(), "style": "points-line"}],
            ref_lines=[{"axis": "y", "value": 0, "name": "Zero"}],
        ),
    ]
    notes = []
    if any(k == "c" for k in kinds):
        notes.append("Categorical terms use effect coding: each estimate is that level minus the average of all levels.")
    if np.nanmax(vif[1:]) > 10:
        notes.append("Some VIF values exceed 10; the X columns are strongly correlated.")
    return Result("fit_model", f"Least squares fit of {y_name}", [summary, anova, estimates, effects], charts, notes)


def _ols(X, y):
    n, p = X.shape
    # QR keeps precision on ill-conditioned designs (for example NIST Longley).
    q, r = np.linalg.qr(X)
    beta = np.linalg.solve(r, q.T @ y)
    rinv = np.linalg.inv(r)
    xtx_inv = rinv @ rinv.T
    resid = y - X @ beta
    sse = float(resid @ resid)
    ymean = float(y.mean())
    sst = float(np.sum((y - ymean) ** 2))
    dfe = n - p
    mse = sse / dfe if dfe > 0 else np.nan
    return beta, sse, ymean, sst, dfe, mse, xtx_inv


def _vif(X):
    """Variance inflation factor for each non-intercept column."""
    p = X.shape[1]
    out = np.full(p, np.nan)
    if p <= 2:
        if p == 2:
            out[1] = 1.0
        return out
    for j in range(1, p):
        others = [i for i in range(p) if i != j]
        Xo = X[:, others]
        b, *_ = np.linalg.lstsq(Xo, X[:, j], rcond=None)
        r = X[:, j] - Xo @ b
        ss = np.sum((X[:, j] - X[:, j].mean()) ** 2)
        r2 = 1 - (r @ r) / ss if ss > 0 else np.nan
        out[j] = 1 / (1 - r2) if r2 < 1 else np.inf
    return out

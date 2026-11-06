"""Shewhart control charts with Western Electric run rules."""

from __future__ import annotations

from math import gamma, sqrt
from typing import Any, Sequence

import numpy as np

from .data import complete_rows, numeric, labels
from .result import AnalysisError, Chart, Result, Table

# d2 and d3 for subgroup sizes 2..25, computed by numerical integration of the
# normal range distribution (they match the 3-decimal tables in Montgomery, App. VI).
_D2 = [1.128379, 1.692569, 2.058751, 2.325929, 2.534413, 2.704357, 2.847201, 2.970026,
       3.077505, 3.172873, 3.258455, 3.335980, 3.406763, 3.471827, 3.531983, 3.587884,
       3.640064, 3.688963, 3.734950, 3.778336, 3.819385, 3.858323, 3.895348, 3.930629]
_D3 = [0.852502, 0.888368, 0.879808, 0.864082, 0.848040, 0.833205, 0.819831, 0.807834,
       0.797051, 0.787315, 0.778478, 0.770416, 0.763023, 0.756211, 0.749908, 0.744052,
       0.738591, 0.733481, 0.728686, 0.724173, 0.719915, 0.715887, 0.712068, 0.708441]


def d2(n: int) -> float:
    _check_n(n)
    return _D2[n - 2]


def d3(n: int) -> float:
    _check_n(n)
    return _D3[n - 2]


def c4(n: int) -> float:
    if n < 2:
        raise AnalysisError("Subgroup size must be at least 2.")
    return sqrt(2 / (n - 1)) * gamma(n / 2) / gamma((n - 1) / 2)


def _check_n(n):
    if not 2 <= n <= 25:
        raise AnalysisError("Subgroup size must be between 2 and 25 for range-based charts.")


RULES = {
    1: "1 point beyond 3 sigma",
    2: "2 of 3 points beyond 2 sigma, same side",
    3: "4 of 5 points beyond 1 sigma, same side",
    4: "8 points in a row on one side of the center line",
}


def western_electric(z: np.ndarray) -> dict[int, list[int]]:
    """Indexes (0-based) of points that complete each rule; ``z`` is in sigma units."""
    hits: dict[int, list[int]] = {k: [] for k in RULES}
    n = z.size
    for i in range(n):
        if abs(z[i]) > 3:
            hits[1].append(i)
        for side in (1, -1):
            if i >= 2:
                w = z[i - 2 : i + 1] * side
                if np.sum(w > 2) >= 2 and z[i] * side > 2:
                    hits[2].append(i)
            if i >= 4:
                w = z[i - 4 : i + 1] * side
                if np.sum(w > 1) >= 4 and z[i] * side > 1:
                    hits[3].append(i)
            if i >= 7:
                w = z[i - 7 : i + 1] * side
                if np.all(w > 0):
                    hits[4].append(i)
    return {k: sorted(set(v)) for k, v in hits.items()}


def _chart(title, ylab, xs, values, center, lcl, ucl, sigma_units, rules=True):
    """One chart spec plus its flagged points. ``lcl``/``ucl`` may be arrays."""
    values = np.asarray(values, dtype=float)
    lcl_a = np.broadcast_to(np.asarray(lcl, dtype=float), values.shape)
    ucl_a = np.broadcast_to(np.asarray(ucl, dtype=float), values.shape)
    flags = western_electric(np.asarray(sigma_units)) if rules else {1: list(np.where((values > ucl_a) | (values < lcl_a))[0])}
    flagged = sorted({i for v in flags.values() for i in v})
    constant = np.all(lcl_a == lcl_a[0]) and np.all(ucl_a == ucl_a[0])
    ref = [{"axis": "y", "value": float(center), "name": "Center"}]
    series = [{"name": ylab, "x": list(xs), "y": values.tolist(), "style": "points-line", "flagged": flagged}]
    if constant:
        ref += [
            {"axis": "y", "value": float(ucl_a[0]), "name": "UCL"},
            {"axis": "y", "value": float(lcl_a[0]), "name": "LCL"},
        ]
    else:
        series += [
            {"name": "UCL", "x": list(xs), "y": ucl_a.tolist(), "style": "step"},
            {"name": "LCL", "x": list(xs), "y": lcl_a.tolist(), "style": "step"},
        ]
    chart = Chart("control", title, x_label="Sample", y_label=ylab, series=series, ref_lines=ref)
    return chart, flags


def _flag_table(chart_name, xs, values, flags):
    rows = []
    for rule, idx in flags.items():
        for i in idx:
            rows.append([chart_name, xs[i], float(values[i]), f"Rule {rule}: {RULES[rule]}"])
    return rows


def _subgroups(values, subgroup, size):
    """Split measurements into subgroups by a label column or a fixed size."""
    if subgroup is not None:
        yv, sg = complete_rows(values, subgroup, kinds="nc")
        order, groups = [], {}
        for v, g in zip(yv, sg):
            if g not in groups:
                groups[g] = []
                order.append(g)
            groups[g].append(v)
        return order, [np.array(groups[g]) for g in order]
    (yv,) = complete_rows(values, kinds="n")
    if not size or size < 2:
        raise AnalysisError("Give a subgroup column or a subgroup size of at least 2.")
    k = yv.size // size
    if k < 2:
        raise AnalysisError("Need at least 2 full subgroups.")
    return [str(i + 1) for i in range(k)], [yv[i * size : (i + 1) * size] for i in range(k)]


# --------------------------------------------------------------------------- charts


def imr(values: Sequence[Any], name: str = "Y", labels_col: Sequence[Any] | None = None) -> Result:
    """Individuals and moving range chart."""
    (x,) = complete_rows(values, kinds="n")
    n = x.size
    if n < 3:
        raise AnalysisError("Need at least 3 values for an individuals chart.")
    xs = list(range(1, n + 1)) if labels_col is None else [l for l, v in zip(labels(labels_col), numeric(values)) if not np.isnan(v)]
    mr = np.abs(np.diff(x))
    mrbar = mr.mean()
    sigma = mrbar / d2(2)
    center = x.mean()
    ucl, lcl = center + 3 * sigma, center - 3 * sigma
    mr_ucl = (1 + 3 * d3(2) / d2(2)) * mrbar  # D4 for n = 2 is 3.267

    c1, f1 = _chart(f"Individuals of {name}", name, xs, x, center, lcl, ucl, (x - center) / sigma if sigma > 0 else np.zeros(n))
    mr_x = xs[1:]
    c2, f2 = _chart("Moving range", "Moving range", mr_x, mr, mrbar, 0.0, mr_ucl, None, rules=False)
    limits = Table(
        "Control limits",
        ["Chart", "LCL", "Center", "UCL", "Sigma estimate"],
        [[f"Individuals of {name}", lcl, center, ucl, sigma], ["Moving range", 0.0, mrbar, mr_ucl, None]],
    )
    flags = Table(
        "Out-of-control points",
        ["Chart", "Sample", "Value", "Rule"],
        _flag_table(f"Individuals of {name}", xs, x, f1) + _flag_table("Moving range", mr_x, mr, f2),
    )
    return Result("imr", f"Individuals and moving range chart of {name}", [limits, flags], [c1, c2])


def xbar_r(values, subgroup=None, size=None, name="Y") -> Result:
    keys, groups = _subgroups(values, subgroup, size)
    ns = np.array([g.size for g in groups])
    if np.any(ns < 2):
        raise AnalysisError("Every subgroup needs at least 2 values for an X̄-R chart.")
    means = np.array([g.mean() for g in groups])
    ranges = np.array([np.ptp(g) for g in groups])
    # Unbiased pooled sigma from ranges, handling unequal subgroup sizes.
    d2s = np.array([d2(int(k)) for k in ns])
    d3s = np.array([d3(int(k)) for k in ns])
    sigma = np.mean(ranges / d2s)
    xbb = float(np.sum(means * ns) / ns.sum())
    se = sigma / np.sqrt(ns)
    ucl, lcl = xbb + 3 * se, xbb - 3 * se
    rcenter = sigma * d2s
    r_ucl = rcenter + 3 * d3s * sigma
    r_lcl = np.maximum(rcenter - 3 * d3s * sigma, 0.0)
    c1, f1 = _chart(f"X̄ of {name}", "Mean", keys, means, xbb, lcl, ucl, (means - xbb) / se)
    c2, f2 = _chart(f"Range of {name}", "Range", keys, ranges, float(np.mean(rcenter)), r_lcl, r_ucl, None, rules=False)
    equal = np.all(ns == ns[0])
    limits = Table(
        "Control limits",
        ["Chart", "LCL", "Center", "UCL", "Sigma estimate", "Subgroup size"],
        [
            ["X̄", float(lcl[0]) if equal else None, xbb, float(ucl[0]) if equal else None, sigma, int(ns[0]) if equal else "varies"],
            ["Range", float(r_lcl[0]) if equal else None, float(np.mean(rcenter)), float(r_ucl[0]) if equal else None, None, int(ns[0]) if equal else "varies"],
        ],
    )
    flags = Table(
        "Out-of-control points",
        ["Chart", "Sample", "Value", "Rule"],
        _flag_table("X̄", keys, means, f1) + _flag_table("Range", keys, ranges, f2),
    )
    return Result("xbar_r", f"X̄ and R chart of {name}", [limits, flags], [c1, c2])


def xbar_s(values, subgroup=None, size=None, name="Y") -> Result:
    keys, groups = _subgroups(values, subgroup, size)
    ns = np.array([g.size for g in groups])
    if np.any(ns < 2):
        raise AnalysisError("Every subgroup needs at least 2 values for an X̄-S chart.")
    means = np.array([g.mean() for g in groups])
    sds = np.array([g.std(ddof=1) for g in groups])
    c4s = np.array([c4(int(k)) for k in ns])
    sigma = float(np.mean(sds / c4s))
    xbb = float(np.sum(means * ns) / ns.sum())
    se = sigma / np.sqrt(ns)
    ucl, lcl = xbb + 3 * se, xbb - 3 * se
    scenter = c4s * sigma
    sspread = 3 * sigma * np.sqrt(1 - c4s**2)
    s_ucl, s_lcl = scenter + sspread, np.maximum(scenter - sspread, 0.0)
    c1, f1 = _chart(f"X̄ of {name}", "Mean", keys, means, xbb, lcl, ucl, (means - xbb) / se)
    c2, f2 = _chart(f"Std dev of {name}", "Std dev", keys, sds, float(np.mean(scenter)), s_lcl, s_ucl, None, rules=False)
    equal = np.all(ns == ns[0])
    limits = Table(
        "Control limits",
        ["Chart", "LCL", "Center", "UCL", "Sigma estimate", "Subgroup size"],
        [
            ["X̄", float(lcl[0]) if equal else None, xbb, float(ucl[0]) if equal else None, sigma, int(ns[0]) if equal else "varies"],
            ["S", float(s_lcl[0]) if equal else None, float(np.mean(scenter)), float(s_ucl[0]) if equal else None, None, int(ns[0]) if equal else "varies"],
        ],
    )
    flags = Table(
        "Out-of-control points",
        ["Chart", "Sample", "Value", "Rule"],
        _flag_table("X̄", keys, means, f1) + _flag_table("S", keys, sds, f2),
    )
    return Result("xbar_s", f"X̄ and S chart of {name}", [limits, flags], [c1, c2])


def p_chart(defectives, sample_sizes, name="Defectives", labels_col=None) -> Result:
    d, nn = complete_rows(defectives, sample_sizes, kinds="nn")
    if d.size < 2:
        raise AnalysisError("Need at least 2 samples for a p chart.")
    if np.any(nn <= 0) or np.any(d < 0) or np.any(d > nn):
        raise AnalysisError("Each sample size must be positive and at least the number of defectives.")
    xs = list(range(1, d.size + 1)) if labels_col is None else labels(labels_col)[: d.size]
    p = d / nn
    pbar = float(d.sum() / nn.sum())
    sig = np.sqrt(pbar * (1 - pbar) / nn)
    ucl = np.minimum(pbar + 3 * sig, 1.0)
    lcl = np.maximum(pbar - 3 * sig, 0.0)
    z = np.where(sig > 0, (p - pbar) / np.where(sig > 0, sig, 1), 0.0)
    c, f = _chart(f"Proportion {name}", "Proportion", xs, p, pbar, lcl, ucl, z)
    equal = np.all(nn == nn[0])
    limits = Table(
        "Control limits",
        ["Chart", "LCL", "Center", "UCL", "Sample size"],
        [["p", float(lcl[0]) if equal else "varies", pbar, float(ucl[0]) if equal else "varies", int(nn[0]) if equal else "varies"]],
    )
    flags = Table("Out-of-control points", ["Chart", "Sample", "Value", "Rule"], _flag_table("p", xs, p, f))
    return Result("p_chart", f"p chart of {name}", [limits, flags], [c])


def c_chart(counts, name="Defects", labels_col=None) -> Result:
    (cv,) = complete_rows(counts, kinds="n")
    if cv.size < 2:
        raise AnalysisError("Need at least 2 samples for a c chart.")
    xs = list(range(1, cv.size + 1)) if labels_col is None else labels(labels_col)[: cv.size]
    cbar = float(cv.mean())
    sig = sqrt(cbar)
    ucl, lcl = cbar + 3 * sig, max(cbar - 3 * sig, 0.0)
    ch, f = _chart(f"Count of {name}", "Count", xs, cv, cbar, lcl, ucl, (cv - cbar) / sig if sig > 0 else np.zeros(cv.size))
    limits = Table("Control limits", ["Chart", "LCL", "Center", "UCL"], [["c", lcl, cbar, ucl]])
    flags = Table("Out-of-control points", ["Chart", "Sample", "Value", "Rule"], _flag_table("c", xs, cv, f))
    return Result("c_chart", f"c chart of {name}", [limits, flags], [ch])

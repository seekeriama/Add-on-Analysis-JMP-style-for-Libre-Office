"""Two-level factorial designs: generate a design, then analyse the responses."""

from __future__ import annotations

import itertools
from typing import Any, Mapping, Sequence

import numpy as np
from scipy import stats

from .data import complete_rows
from .result import AnalysisError, Chart, Result, Table

LETTERS = "ABCDEFGHJKLM"

# Generators giving the highest resolution for each (factors, runs) pair
# (Montgomery, Design and Analysis of Experiments, Table 8.14).
GENERATORS: dict[tuple[int, int], list[str]] = {
    (3, 4): ["AB"],
    (4, 8): ["ABC"],
    (5, 16): ["ABCD"],
    (5, 8): ["AB", "AC"],
    (6, 32): ["ABCDE"],
    (6, 16): ["ABC", "BCD"],
    (6, 8): ["AB", "AC", "BC"],
    (7, 64): ["ABCDEF"],
    (7, 32): ["ABCD", "ABDE"],
    (7, 16): ["ABC", "BCD", "ACD"],
    (7, 8): ["AB", "AC", "BC", "ABC"],
}
RESOLUTION = {
    (3, 4): "III", (4, 8): "IV", (5, 16): "V", (5, 8): "III", (6, 32): "VI", (6, 16): "IV",
    (6, 8): "III", (7, 64): "VII", (7, 32): "IV", (7, 16): "IV", (7, 8): "III",
}


def design_options(k: int) -> list[dict]:
    """Run counts available for ``k`` factors."""
    opts = [{"runs": 2**k, "type": "Full factorial", "resolution": "Full"}] if k <= 7 else []
    for (kk, runs), _ in GENERATORS.items():
        if kk == k:
            opts.append({"runs": runs, "type": f"2^({k}-{int(np.log2(2**k // runs))}) fractional", "resolution": RESOLUTION[(k, runs)]})
    return sorted(opts, key=lambda o: o["runs"])


def generate(
    factors: Sequence[Mapping[str, Any]],
    runs: int | None = None,
    center_points: int = 0,
    replicates: int = 1,
    randomize: bool = True,
    seed: int | None = None,
) -> Result:
    """``factors``: list of {"name", "low", "high"}. Returns the run sheet as a table."""
    k = len(factors)
    if not 2 <= k <= 7:
        raise AnalysisError("Choose between 2 and 7 factors.")
    runs = runs or 2**k
    base_k = k
    gens: list[str] = []
    if runs != 2**k:
        if (k, runs) not in GENERATORS:
            avail = ", ".join(str(o["runs"]) for o in design_options(k))
            raise AnalysisError(f"{runs} runs is not available for {k} factors. Choose one of: {avail}.")
        gens = GENERATORS[(k, runs)]
        base_k = k - len(gens)
    base = np.array(list(itertools.product([-1, 1], repeat=base_k)))[:, ::-1]  # standard (Yates) order
    cols = [base[:, i] for i in range(base_k)]
    for g in gens:
        cols.append(np.prod([cols[LETTERS.index(ch)] for ch in g], axis=0))
    coded = np.column_stack(cols)
    coded = np.tile(coded, (replicates, 1))
    if center_points:
        coded = np.vstack([coded, np.zeros((center_points, k))])
    std_order = np.arange(1, coded.shape[0] + 1)
    order = np.arange(coded.shape[0])
    if randomize:
        order = np.random.default_rng(seed).permutation(order)

    names = [str(f["name"]) for f in factors]
    rows = []
    for run_no, i in enumerate(order, start=1):
        actual = []
        for j, f in enumerate(factors):
            lo, hi = float(f["low"]), float(f["high"])
            actual.append(lo + (coded[i, j] + 1) / 2 * (hi - lo))
        rows.append([run_no, int(std_order[i]), *actual, None])
    sheet = Table("Design", ["Run", "Std order", *names, "Response"], rows)
    alias = []
    for g, letter in zip(gens, LETTERS[base_k:k]):
        alias.append([f"{letter} = {g}", f"I = {g}{letter}"])
    info = Table(
        "Design summary",
        ["Property", "Value"],
        [
            ["Factors", k],
            ["Runs", int(coded.shape[0])],
            ["Type", "Full factorial" if not gens else f"2^({k}-{len(gens)}) fractional factorial"],
            ["Resolution", RESOLUTION.get((k, runs), "Full")],
            ["Center points", center_points],
            ["Replicates", replicates],
            ["Factor key", ", ".join(f"{LETTERS[i]} = {n}" for i, n in enumerate(names))],
        ],
    )
    tables = [info, sheet]
    if alias:
        tables.append(Table("Generators", ["Generator", "Defining relation word"], alias))
    return Result("doe_design", f"{k}-factor two-level design, {coded.shape[0]} runs", tables, [],
                  ["Fill the Response column, then run Analyze screening design on the sheet."])


def analyze(
    response: Sequence[Any],
    factors: Mapping[str, Sequence[Any]],
    y_name: str = "Response",
    interactions: bool = True,
    alpha: float = 0.05,
) -> Result:
    """Effects of a two-level design. Factor columns may hold actual or coded (-1/+1) settings.

    Uses least squares when there are residual degrees of freedom, and Lenth's
    pseudo standard error when the model is saturated.
    """
    names = list(factors)
    if not names:
        raise AnalysisError("Choose the factor columns.")
    cols = complete_rows(response, *[factors[n] for n in names], kinds="n" * (len(names) + 1))
    y = cols[0]
    coded = []
    for nm, c in zip(names, cols[1:]):
        lo, hi = float(np.min(c)), float(np.max(c))
        if lo == hi:
            raise AnalysisError(f"{nm} has only one setting.")
        mid, half = (lo + hi) / 2, (hi - lo) / 2
        coded.append((c - mid) / half)
    X_main = np.column_stack(coded)

    terms = list(names)
    mats = [X_main[:, i] for i in range(len(names))]
    if interactions:
        for i, j in itertools.combinations(range(len(names)), 2):
            v = X_main[:, i] * X_main[:, j]
            if any(np.allclose(np.abs(v), np.abs(m)) and abs(np.dot(v, m)) / len(v) > 0.999 for m in mats):
                continue  # aliased with a term already in the model
            terms.append(f"{names[i]}×{names[j]}")
            mats.append(v)
    X = np.column_stack([np.ones(y.size), *mats])
    if np.linalg.matrix_rank(X) < X.shape[1]:
        # Drop aliased interactions until the model is estimable.
        keep = [0]
        for c in range(1, X.shape[1]):
            if np.linalg.matrix_rank(X[:, keep + [c]]) == len(keep) + 1:
                keep.append(c)
        terms = [terms[c - 1] for c in keep[1:]]
        X = X[:, keep]
    n, p = X.shape
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    effects = 2 * beta[1:]
    dfe = n - p
    rows = []
    method = ""
    if dfe > 0:
        resid = y - X @ beta
        mse = float(resid @ resid) / dfe
        se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * mse)
        t = beta / se
        pv = 2 * stats.t.sf(np.abs(t), dfe)
        for i, term in enumerate(terms, start=1):
            rows.append([term, effects[i - 1], beta[i], se[i], t[i], pv[i]])
        method = f"Least squares, {dfe} error DF"
        cols_ = ["Term", "Effect", "Coefficient", "Std error", "t ratio", "p-value"]
    else:
        abs_c = np.abs(beta[1:])
        s0 = 1.5 * np.median(abs_c)
        pse = 1.5 * np.median(abs_c[abs_c < 2.5 * s0]) if np.any(abs_c < 2.5 * s0) else s0
        d = len(terms) / 3
        for i, term in enumerate(terms, start=1):
            t = beta[i] / pse if pse > 0 else np.inf
            rows.append([term, effects[i - 1], beta[i], pse, t, 2 * stats.t.sf(abs(t), d)])
        method = "Saturated model: Lenth's pseudo standard error"
        cols_ = ["Term", "Effect", "Coefficient", "Lenth PSE", "t ratio", "p-value (Lenth)"]
    rows.sort(key=lambda r: -abs(r[1]))
    est = Table("Effect estimates", cols_, rows)
    info = Table("Model", ["Statistic", "Value"], [["Runs", n], ["Terms", len(terms)], ["Method", method], ["Mean", float(y.mean())]])

    # Half-normal plot of absolute effects.
    abs_eff = np.sort(np.abs(effects))
    m = abs_eff.size
    hn = stats.norm.ppf(0.5 + 0.5 * (np.arange(1, m + 1) - 0.5) / m)
    order = np.argsort(np.abs(effects))
    charts = [
        Chart(
            "bar",
            f"Pareto of effects on {y_name}",
            x_label="Term",
            y_label="|Effect|",
            series=[{"name": "|Effect|", "x": [r[0] for r in rows], "y": [abs(r[1]) for r in rows]}],
            extra={"horizontal": True},
        ),
        Chart(
            "scatter",
            "Half-normal plot",
            x_label="Half-normal quantile",
            y_label="|Effect|",
            series=[{"name": "Effects", "x": hn.tolist(), "y": abs_eff.tolist(), "labels": [terms[i] for i in order], "style": "points"}],
        ),
        Chart(
            "line",
            "Main effects",
            x_label="Coded level",
            y_label=f"Mean {y_name}",
            series=[
                {"name": nm, "x": [-1, 1], "y": [float(y[X_main[:, i] < 0].mean()), float(y[X_main[:, i] > 0].mean())], "style": "points-line"}
                for i, nm in enumerate(names)
            ],
        ),
    ]
    return Result("doe_analysis", f"Screening analysis of {y_name}", [info, est], charts)

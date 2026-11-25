"""One JSON-in, JSON-out entry point shared by every host adapter.

Request shape::

    {
      "analysis": "distribution",
      "columns": {"Weight": [1.2, 3.4, ...], "Batch": ["A", "B", ...]},
      "roles": {"y": ["Weight"], "x": ["Batch"]},
      "options": {"confidence": 0.95}
    }

Response: ``{"ok": true, "result": {...}}`` or ``{"ok": false, "error": "..."}``.
"""

from __future__ import annotations

import json
import traceback
from typing import Any, Callable

from . import bivariate, capability, control, distribution, doe, msa, regression, tables, tree
from .result import AnalysisError, Result


def _col(req, role, idx=0, required=True):
    names = req.get("roles", {}).get(role) or []
    if isinstance(names, str):
        names = [names]
    if len(names) <= idx:
        if required:
            raise AnalysisError(f"Choose a column for the '{role}' role.")
        return None, None
    name = names[idx]
    cols = req.get("columns", {})
    if name not in cols:
        raise AnalysisError(f"Column '{name}' was not sent with the request.")
    return name, cols[name]


def _types(req):
    return req.get("options", {}).get("types", {}) or {}


def _distribution(req):
    opts = req.get("options", {})
    out = []
    names = req.get("roles", {}).get("y") or []
    if not names:
        raise AnalysisError("Choose at least one Y column.")
    for i in range(len(names)):
        name, col = _col(req, "y", i)
        out.append(distribution.distribution(col, name, opts.get("confidence", 0.95), opts.get("bins", "auto")))
    return out


def _fit_y_by_x(req):
    yn, y = _col(req, "y")
    xn, x = _col(req, "x")
    t = _types(req)
    return bivariate.fit_y_by_x(y, x, yn, xn, t.get(yn), t.get(xn), req.get("options", {}).get("confidence", 0.95))


def _fit_model(req):
    yn, y = _col(req, "y")
    xnames = req.get("roles", {}).get("x") or []
    xs = {nm: req["columns"][nm] for nm in xnames}
    return regression.fit_model(y, xs, yn, _types(req), req.get("options", {}).get("confidence", 0.95))


def _control(req):
    opts = req.get("options", {})
    kind = opts.get("chart", "imr")
    yn, y = _col(req, "y")
    if kind == "imr":
        _, lab = _col(req, "label", required=False)
        return control.imr(y, yn, lab)
    if kind in ("xbar_r", "xbar_s"):
        _, sg = _col(req, "subgroup", required=False)
        fn = control.xbar_r if kind == "xbar_r" else control.xbar_s
        return fn(y, sg, opts.get("subgroup_size"), yn)
    if kind == "p":
        _, n = _col(req, "n")
        return control.p_chart(y, n, yn)
    if kind == "c":
        return control.c_chart(y, yn)
    raise AnalysisError(f"Unknown control chart type '{kind}'.")


def _gauge_rr(req):
    yn, y = _col(req, "y")
    _, part = _col(req, "part")
    _, op = _col(req, "operator")
    o = req.get("options", {})
    return msa.gauge_rr(y, part, op, yn, o.get("tolerance"), o.get("study_multiplier", 6.0), o.get("alpha_interaction", 0.25))


def _capability(req):
    yn, y = _col(req, "y")
    _, sg = _col(req, "subgroup", required=False)
    o = req.get("options", {})
    return capability.capability(y, o.get("lsl"), o.get("usl"), o.get("target"), sg, o.get("subgroup_size"), yn, o.get("confidence", 0.95))


def _doe_design(req):
    o = req.get("options", {})
    return doe.generate(o.get("factors", []), o.get("runs"), o.get("center_points", 0), o.get("replicates", 1), o.get("randomize", True), o.get("seed"))


def _doe_analyze(req):
    yn, y = _col(req, "y")
    xnames = req.get("roles", {}).get("x") or []
    return doe.analyze(y, {nm: req["columns"][nm] for nm in xnames}, yn, req.get("options", {}).get("interactions", True))


def _tree(req):
    yn, y = _col(req, "y")
    xnames = req.get("roles", {}).get("x") or []
    o = req.get("options", {})
    t = _types(req)
    return tree.decision_tree(
        y, {nm: req["columns"][nm] for nm in xnames}, yn, t.get(yn), t,
        o.get("max_depth", 3), o.get("min_leaf", 5), o.get("validation", 0.0), o.get("seed", 1),
    )


# ------------------------------------------------------------- table tools
# These receive every column of the table in "columns" (and of a second table
# in "columns_b" for two-table tools) because the output keeps all of them.


def _names(req, role):
    v = req.get("roles", {}).get(role) or []
    return [v] if isinstance(v, str) else list(v)


def _one(req, role):
    v = _names(req, role)
    return v[0] if v else None


def _a(req):
    cols = req.get("columns") or {}
    if not cols:
        raise AnalysisError("Choose the data table first.")
    return cols


def _b(req):
    cols = req.get("columns_b") or {}
    if not cols:
        raise AnalysisError("Choose the second table: select it in the sheet, then press Use selection under Second table.")
    return cols


def _opt(req, key, default=None):
    v = req.get("options", {}).get(key, default)
    return default if v is None else v


def _int_or_none(v):
    return None if v in (None, "") else int(v)


def _summary(req):
    return tables.summary(_a(req), _names(req, "group"), _names(req, "y"), _opt(req, "stats", ["n", "mean", "std", "min", "max"]))


def _subset(req):
    return tables.subset(
        _a(req), _names(req, "keep"), _one(req, "where"), _opt(req, "op", "eq"), _opt(req, "value"),
        _opt(req, "sample", "all"), _int_or_none(_opt(req, "count")), _opt(req, "fraction"), _int_or_none(_opt(req, "seed")),
    )


def _sort(req):
    by = [(_one(req, r), bool(_opt(req, d, False))) for r, d in (("by", "desc"), ("by2", "desc2"), ("by3", "desc3"))]
    return tables.sort(_a(req), [(c, d) for c, d in by if c])


def _stack(req):
    return tables.stack(_a(req), _names(req, "stack"), _opt(req, "data_name", "Data"), _opt(req, "label_name", "Label"), bool(_opt(req, "drop_missing", False)))


def _split(req):
    return tables.split(_a(req), _names(req, "split"), _one(req, "by"), _names(req, "group"))


def _transpose(req):
    return tables.transpose(_a(req), _names(req, "columns"), _one(req, "label"))


def _join(req):
    return tables.join(_a(req), _b(req), _names(req, "key"), _names(req, "key_b"), _opt(req, "how", "inner"))


def _update(req):
    return tables.update(
        _a(req), _b(req), _names(req, "key"), _names(req, "key_b"), _opt(req, "match", "key") == "row",
        bool(_opt(req, "ignore_missing", True)), bool(_opt(req, "add_columns", False)),
    )


def _concatenate(req):
    return tables.concatenate(_a(req), _b(req), bool(_opt(req, "source_column", False)), _opt(req, "source_a", "Table 1"), _opt(req, "source_b", "Table 2"))


def _missing_pattern(req):
    return tables.missing_pattern(_a(req), _names(req, "columns"))


def _compare(req):
    return tables.compare(_a(req), _b(req), _names(req, "key"), _names(req, "key_b"), _opt(req, "source_a", "Table 1"), _opt(req, "source_b", "Table 2"))


def _anonymize(req):
    return tables.anonymize(
        _a(req), _names(req, "columns"), bool(_opt(req, "rename", True)), _opt(req, "numeric", "rescale"),
        _int_or_none(_opt(req, "seed")), bool(_opt(req, "include_key", False)),
    )


ANALYSES: dict[str, Callable[[dict], Any]] = {
    "distribution": _distribution,
    "fit_y_by_x": _fit_y_by_x,
    "fit_model": _fit_model,
    "control_chart": _control,
    "capability": _capability,
    "gauge_rr": _gauge_rr,
    "doe_design": _doe_design,
    "doe_analyze": _doe_analyze,
    "decision_tree": _tree,
    "summary": _summary,
    "subset": _subset,
    "sort": _sort,
    "stack": _stack,
    "split": _split,
    "transpose": _transpose,
    "join": _join,
    "update": _update,
    "concatenate": _concatenate,
    "missing_pattern": _missing_pattern,
    "compare": _compare,
    "anonymize": _anonymize,
}


def run(request: dict) -> dict:
    try:
        name = request.get("analysis")
        if name not in ANALYSES:
            raise AnalysisError(f"Unknown analysis '{name}'. Choose one of: {', '.join(ANALYSES)}.")
        out = ANALYSES[name](request)
        results = out if isinstance(out, list) else [out]
        return {"ok": True, "results": [r.to_dict() for r in results]}
    except AnalysisError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # pragma: no cover - shown to the user, logged for bug reports
        return {"ok": False, "error": f"Internal error: {e}", "trace": traceback.format_exc()}


def run_json(request_json: str) -> str:
    """String version for hosts that pass JSON across a language boundary (Pyodide, UNO)."""
    return json.dumps(run(json.loads(request_json)), allow_nan=False)

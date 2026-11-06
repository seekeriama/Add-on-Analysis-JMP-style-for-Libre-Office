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

from . import bivariate, capability, control, distribution, doe, msa, regression, tree
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

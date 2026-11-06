"""Decision tree (recursive partitioning) for a numeric or categorical response.

Uses scikit-learn's CART implementation (BSD-3), imported lazily so the rest of
the core works without it.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from .data import complete_rows, is_numeric_column, ordered_levels
from .result import AnalysisError, Chart, Result, Table


def decision_tree(
    y: Sequence[Any],
    xs: Mapping[str, Sequence[Any]],
    y_name: str = "Y",
    y_type: str | None = None,
    x_types: Mapping[str, str] | None = None,
    max_depth: int = 3,
    min_leaf: int = 5,
    validation: float = 0.0,
    seed: int = 1,
) -> Result:
    try:
        from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
    except ImportError as e:  # pragma: no cover
        raise AnalysisError("Decision trees need scikit-learn. Install it with: pip install scikit-learn") from e

    if not xs:
        raise AnalysisError("Choose at least one X column.")
    yt = y_type or ("continuous" if is_numeric_column(y) else "nominal")
    x_types = dict(x_types or {})
    names = list(xs)
    kinds = ["n" if (x_types.get(n) or ("continuous" if is_numeric_column(xs[n]) else "nominal")) == "continuous" else "c" for n in names]
    cols = complete_rows(y, *[xs[n] for n in names], kinds=("n" if yt == "continuous" else "c") + "".join(kinds))
    yv = cols[0]
    n = len(yv)
    if n < 2 * min_leaf:
        raise AnalysisError(f"Need at least {2 * min_leaf} complete rows for a minimum leaf size of {min_leaf}.")

    # One-hot encode categorical X; remember which source column each feature came from.
    feats, feat_names, feat_src, feat_level = [], [], [], []
    for nm, kind, col in zip(names, kinds, cols[1:]):
        if kind == "n":
            feats.append(np.asarray(col, dtype=float))
            feat_names.append(nm)
            feat_src.append(nm)
            feat_level.append(None)
        else:
            arr = np.array(col, dtype=object)
            for lv in ordered_levels(col):
                feats.append((arr == lv).astype(float))
                feat_names.append(f"{nm} = {lv}")
                feat_src.append(nm)
                feat_level.append(lv)
    X = np.column_stack(feats)

    classify = yt != "continuous"
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    n_val = int(round(n * validation)) if 0 < validation < 0.5 else 0
    val_idx, train_idx = idx[:n_val], idx[n_val:]
    if classify:
        classes = ordered_levels(yv)
        y_arr = np.array([classes.index(v) for v in yv])
        model = DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=min_leaf, random_state=seed)
    else:
        y_arr = np.asarray(yv, dtype=float)
        model = DecisionTreeRegressor(max_depth=max_depth, min_samples_leaf=min_leaf, random_state=seed)
    model.fit(X[train_idx], y_arr[train_idx])
    t = model.tree_

    def describe(node, left):
        f = t.feature[node]
        thr = t.threshold[node]
        if feat_level[f] is not None:
            return f"{feat_src[f]} {'≠' if left else '='} {feat_level[f]}"
        return f"{feat_names[f]} {'<' if left else '≥'} {thr:.6g}"

    nodes = []
    leaf_rules = []

    def walk(node, parent, rule, path):
        count = int(t.n_node_samples[node])
        if classify:
            probs = t.value[node][0] / t.value[node][0].sum()
            pred = classes[int(np.argmax(probs))]
            detail = ", ".join(f"{c}: {p:.1%}" for c, p in zip(classes, probs))
        else:
            pred = float(t.value[node][0][0])
            detail = f"SD {np.sqrt(t.impurity[node]):.6g}"
        is_leaf = t.children_left[node] == -1
        nodes.append({"id": node, "parent": parent, "rule": rule, "n": count, "prediction": pred, "detail": detail, "leaf": is_leaf})
        if is_leaf:
            leaf_rules.append([" and ".join(path) or "(all rows)", count, pred, detail])
            return
        l_rule, r_rule = describe(node, True), describe(node, False)
        walk(t.children_left[node], node, l_rule, path + [l_rule])
        walk(t.children_right[node], node, r_rule, path + [r_rule])

    walk(0, None, "All rows", [])

    node_table = Table(
        "Tree nodes",
        ["Node", "Parent", "Split", "N", "Prediction", "Detail", "Leaf"],
        [[d["id"], d["parent"], d["rule"], d["n"], d["prediction"], d["detail"], "Yes" if d["leaf"] else ""] for d in nodes],
    )
    rules = Table("Leaf rules", ["Rule", "N", "Prediction", "Detail"], leaf_rules)

    imp: dict[str, float] = {}
    for src, v in zip(feat_src, model.feature_importances_):
        imp[src] = imp.get(src, 0.0) + float(v)
    imp_rows = sorted(([k, v] for k, v in imp.items()), key=lambda r: -r[1])
    importance = Table("Column contributions", ["Column", "Share of improvement"], imp_rows)

    def fit_stats(rows, label):
        if rows.size == 0:
            return []
        pred = model.predict(X[rows])
        if classify:
            return [[f"{label} accuracy", float(np.mean(pred == y_arr[rows]))], [f"{label} rows", int(rows.size)]]
        ss_res = float(np.sum((y_arr[rows] - pred) ** 2))
        ss_tot = float(np.sum((y_arr[rows] - y_arr[rows].mean()) ** 2))
        return [
            [f"{label} R²", 1 - ss_res / ss_tot if ss_tot > 0 else None],
            [f"{label} RMSE", float(np.sqrt(ss_res / rows.size))],
            [f"{label} rows", int(rows.size)],
        ]

    summary = Table(
        "Fit",
        ["Statistic", "Value"],
        [["Type", "Classification" if classify else "Regression"], ["Leaves", int(model.get_n_leaves())], ["Depth", int(model.get_depth())]]
        + fit_stats(train_idx, "Training")
        + fit_stats(val_idx, "Validation"),
    )
    tables = [summary, rules, importance, node_table]
    if classify:
        pred = model.predict(X[train_idx])
        cm = np.zeros((len(classes), len(classes)), dtype=int)
        for a, b in zip(y_arr[train_idx], pred):
            cm[a, b] += 1
        tables.append(Table("Confusion matrix (training): actual rows, predicted columns", ["Actual", *classes], [[c, *cm[i].tolist()] for i, c in enumerate(classes)]))

    charts = [
        Chart("tree", f"Decision tree for {y_name}", series=[{"name": "nodes", "nodes": nodes}]),
        Chart(
            "bar",
            "Column contributions",
            x_label="Column",
            y_label="Share of improvement",
            series=[{"name": "Share", "x": [r[0] for r in imp_rows], "y": [r[1] for r in imp_rows]}],
            extra={"horizontal": True},
        ),
    ]
    notes = [f"Max depth {max_depth}, minimum leaf size {min_leaf}."]
    if n_val:
        notes.append(f"{n_val} randomly chosen rows (seed {seed}) were held out for validation.")
    return Result("decision_tree", f"Decision tree for {y_name}", tables, charts, notes)

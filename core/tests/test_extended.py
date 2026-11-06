"""Gauge R&R, capability, DOE and decision tree."""

import numpy as np
import pytest
from scipy import stats

import cellstat
from cellstat import capability, doe, msa, tree
from cellstat.result import AnalysisError


def grr_data(seed=0, interaction=0.0):
    rng = np.random.default_rng(seed)
    parts = rng.normal(0, 2.0, 10)
    ops = rng.normal(0, 0.5, 3)
    po = rng.normal(0, interaction, (10, 3))
    y, p, o = [], [], []
    for i in range(10):
        for j in range(3):
            for _ in range(3):
                y.append(10 + parts[i] + ops[j] + po[i, j] + rng.normal(0, 0.3))
                p.append(f"P{i + 1}")
                o.append(f"Op{j + 1}")
    return y, p, o


def test_gauge_rr_anova_matches_statsmodels():
    sm = pytest.importorskip("statsmodels.formula.api")
    from statsmodels.stats.anova import anova_lm
    import pandas as pd

    y, p, o = grr_data(interaction=0.6)
    r = msa.gauge_rr(y, p, o, "d")
    df = pd.DataFrame({"y": y, "p": p, "o": o})
    ref = anova_lm(sm.ols("y ~ C(p) * C(o)", df).fit())
    assert r.value("Two-way ANOVA", "Part", "Sum of squares") == pytest.approx(ref.loc["C(p)", "sum_sq"])
    assert r.value("Two-way ANOVA", "Part × Operator", "Sum of squares") == pytest.approx(ref.loc["C(p):C(o)", "sum_sq"])
    assert r.value("Two-way ANOVA", "Repeatability", "Sum of squares") == pytest.approx(ref.loc["Residual", "sum_sq"])
    ms_e = ref.loc["Residual", "mean_sq"]
    ms_po = ref.loc["C(p):C(o)", "mean_sq"]
    assert r.value("Variance components", "  Repeatability", "Variance component") == pytest.approx(ms_e)
    assert r.value("Variance components", "    Part × Operator", "Variance component") == pytest.approx((ms_po - ms_e) / 3)


def test_gauge_rr_pools_weak_interaction_and_sums():
    y, p, o = grr_data(seed=3)
    r = msa.gauge_rr(y, p, o, "d", tolerance=12)
    assert r.value("Summary", "Interaction pooled into repeatability", "Value") == "Yes"
    t = r.table("Variance components")
    contrib = {row[0].strip(): row[2] for row in t.rows}
    assert contrib["Total Gauge R&R"] + contrib["Part-to-part"] == pytest.approx(100)
    assert "% Tolerance" in t.columns
    assert r.value("Summary", "Number of distinct categories", "Value") >= 5


def test_gauge_rr_requires_balance():
    y, p, o = grr_data()
    with pytest.raises(AnalysisError):
        msa.gauge_rr(y[:-1], p[:-1], o[:-1])


def test_capability_indices():
    rng = np.random.default_rng(5)
    x = rng.normal(10, 1, 200)
    r = capability.capability(x.tolist(), lsl=7, usl=14, subgroup_size=5, name="x")
    s = x.std(ddof=1)
    m = x.mean()
    assert r.value("Capability indices", "Cp / Pp", "Overall") == pytest.approx(7 / (6 * s))
    assert r.value("Capability indices", "Cpk / Ppk", "Overall") == pytest.approx(min(m - 7, 14 - m) / (3 * s))
    sw = np.ptp(x.reshape(40, 5), axis=1).mean() / 2.325929
    assert r.value("Capability indices", "Cp / Pp", "Within") == pytest.approx(7 / (6 * sw))
    exp = (stats.norm.cdf((7 - m) / s) + stats.norm.sf((14 - m) / s)) * 1e6
    assert r.value("Nonconforming parts per million", "Total", "Expected overall") == pytest.approx(exp)


def test_capability_one_sided():
    r = capability.capability([1, 2, 3, 2, 3, 2, 1, 2], usl=6)
    assert r.value("Capability indices", "Cp / Pp", "Overall") is None
    assert r.value("Capability indices", "Cpk / Ppk", "Overall") == r.value("Capability indices", "CPU / PPU", "Overall")


def test_full_factorial_is_orthogonal_and_balanced():
    f = [{"name": "Temp", "low": 150, "high": 200}, {"name": "Time", "low": 10, "high": 20}, {"name": "Speed", "low": 1, "high": 3}]
    r = doe.generate(f, randomize=False)
    rows = r.table("Design").rows
    assert len(rows) == 8
    assert rows[0][2:5] == [150, 10, 1] and rows[-1][2:5] == [200, 20, 3]


def test_fractional_design_generator():
    f = [{"name": c, "low": -1, "high": 1} for c in "PQRST"]
    r = doe.generate(f, runs=16, randomize=False)
    X = np.array([row[2:7] for row in r.table("Design").rows])
    assert X.shape == (16, 5)
    assert np.allclose(X[:, 4], X[:, 0] * X[:, 1] * X[:, 2] * X[:, 3])  # E = ABCD
    assert np.allclose(X.T @ X, 16 * np.eye(5))
    assert r.value("Design summary", "Resolution", "Value") == "V"
    with pytest.raises(AnalysisError):
        doe.generate(f, runs=4)


def test_doe_analysis_recovers_effects():
    f = [{"name": c, "low": 0, "high": 10} for c in "ABC"]
    d = doe.generate(f, replicates=2, randomize=False).table("Design").rows
    rng = np.random.default_rng(2)
    A = np.array([r[2] for r in d]) / 5 - 1
    B = np.array([r[3] for r in d]) / 5 - 1
    y = 50 + 4 * A - 2 * B + 1.5 * A * B + rng.normal(0, 0.05, A.size)
    r = doe.analyze(y.tolist(), {"A": [r[2] for r in d], "B": [r[3] for r in d], "C": [r[4] for r in d]})
    assert r.value("Effect estimates", "A", "Effect") == pytest.approx(8, abs=0.1)
    assert r.value("Effect estimates", "B", "Effect") == pytest.approx(-4, abs=0.1)
    assert r.value("Effect estimates", "A×B", "Effect") == pytest.approx(3, abs=0.1)
    assert r.value("Effect estimates", "C", "p-value") > 0.01


def test_doe_saturated_uses_lenth():
    f = [{"name": c, "low": -1, "high": 1} for c in "ABCDEFG"]
    d = doe.generate(f, runs=8, randomize=False).table("Design").rows
    X = np.array([r[2:9] for r in d])
    y = 10 + 3 * X[:, 0] + np.random.default_rng(1).normal(0, 0.1, 8)
    r = doe.analyze(y.tolist(), {c: X[:, i].tolist() for i, c in enumerate("ABCDEFG")}, interactions=False)
    assert "Lenth" in r.value("Model", "Method", "Value")
    assert r.table("Effect estimates").rows[0][0] == "A"


def test_decision_tree_classification():
    pytest.importorskip("sklearn")
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 10, 200)
    g = rng.choice(["red", "blue"], 200)
    y = np.where((x > 5) & (g == "red"), "fail", "pass")
    r = tree.decision_tree(y.tolist(), {"x": x.tolist(), "color": g.tolist()}, "result", max_depth=2, validation=0.25)
    assert r.value("Fit", "Training accuracy", "Value") == 1.0
    assert {row[0] for row in r.table("Column contributions").rows} == {"x", "color"}
    assert any("color" in row[0] for row in r.table("Leaf rules").rows)


def test_decision_tree_regression_via_api():
    pytest.importorskip("sklearn")
    rng = np.random.default_rng(1)
    x = rng.uniform(0, 1, 100)
    y = np.where(x > 0.5, 10, 0) + rng.normal(0, 0.1, 100)
    out = cellstat.run({"analysis": "decision_tree", "columns": {"y": y.tolist(), "x": x.tolist()}, "roles": {"y": ["y"], "x": ["x"]}, "options": {"max_depth": 1}})
    assert out["ok"], out
    fit = {r[0]: r[1] for r in out["results"][0]["tables"][0]["rows"]}
    assert fit["Training R²"] > 0.99

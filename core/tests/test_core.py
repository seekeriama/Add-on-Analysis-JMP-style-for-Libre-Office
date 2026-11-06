"""Checks against certified or published reference values.

* NIST StRD Longley: https://www.itl.nist.gov/div898/strd/lls/data/Longley.shtml
* R PlantGrowth dataset: values from R's aov, TukeyHSD, bartlett.test, oneway.test
* Control chart constants: Montgomery, Introduction to Statistical Quality Control, App. VI
"""

import json
import math

import numpy as np
import pytest
from scipy import stats

import cellstat
from cellstat import bivariate, control, distribution, regression
from cellstat.result import AnalysisError

LONGLEY = [
    # y, x1..x6
    (60323, 83.0, 234289, 2356, 1590, 107608, 1947),
    (61122, 88.5, 259426, 2325, 1456, 108632, 1948),
    (60171, 88.2, 258054, 3682, 1616, 109773, 1949),
    (61187, 89.5, 284599, 3351, 1650, 110929, 1950),
    (63221, 96.2, 328975, 2099, 3099, 112075, 1951),
    (63639, 98.1, 346999, 1932, 3594, 113270, 1952),
    (64989, 99.0, 365385, 1870, 3547, 115094, 1953),
    (63761, 100.0, 363112, 3578, 3350, 116219, 1954),
    (66019, 101.2, 397469, 2904, 3048, 117388, 1955),
    (67857, 104.6, 419180, 2822, 2857, 118734, 1956),
    (68169, 108.4, 442769, 2936, 2798, 120445, 1957),
    (66513, 110.8, 444546, 4681, 2637, 121950, 1958),
    (68655, 112.6, 482704, 3813, 2552, 123366, 1959),
    (69564, 114.2, 502601, 3931, 2514, 125368, 1960),
    (69331, 115.7, 518173, 4806, 2572, 127852, 1961),
    (70551, 116.9, 554894, 4007, 2827, 130081, 1962),
]

PLANT = {
    "ctrl": [4.17, 5.58, 5.18, 6.11, 4.50, 4.61, 5.17, 4.53, 5.33, 5.14],
    "trt1": [4.81, 4.17, 4.41, 3.59, 5.87, 3.83, 6.03, 4.89, 4.32, 4.69],
    "trt2": [6.31, 5.12, 5.54, 5.50, 5.37, 5.29, 4.92, 6.15, 5.80, 5.26],
}


def plant_columns():
    y, g = [], []
    for k, v in PLANT.items():
        y += v
        g += [k] * len(v)
    return y, g


# ----------------------------------------------------------------------------- regression


def test_longley_certified_values():
    cols = list(zip(*LONGLEY))
    xs = {f"x{i}": list(cols[i]) for i in range(1, 7)}
    r = regression.fit_model(list(cols[0]), xs, "y")
    certified = [
        ("Intercept", -3482258.63459582, 890420.383607373),
        ("x1", 15.0618722713733, 84.9149257747669),
        ("x2", -0.358191792925910e-01, 0.334910077722432e-01),
        ("x3", -2.02022980381683, 0.488399681651699),
        ("x4", -1.03322686717359, 0.214274163161675),
        ("x5", -0.511041056535807e-01, 0.226073200069370),
        ("x6", 1829.15146461355, 455.478499142212),
    ]
    for term, est, se in certified:
        assert r.value("Parameter estimates", term, "Estimate") == pytest.approx(est, rel=1e-8)
        assert r.value("Parameter estimates", term, "Std error") == pytest.approx(se, rel=1e-8)
    assert r.value("Summary of fit", "R²", "Value") == pytest.approx(0.995479004577296, rel=1e-10)
    assert r.value("Summary of fit", "Root mean square error", "Value") == pytest.approx(304.854073561965, rel=1e-9)
    assert r.value("Analysis of variance", "Model", "Sum of squares") == pytest.approx(184172401.944494, rel=1e-9)
    assert r.value("Analysis of variance", "Error", "Sum of squares") == pytest.approx(836424.055505915, rel=1e-8)


def test_fit_model_categorical_matches_oneway():
    y, g = plant_columns()
    r = regression.fit_model(y, {"group": g}, "weight")
    assert r.value("Effect tests", "group", "F ratio") == pytest.approx(4.846088, rel=1e-6)
    # Effect coding: intercept is the mean of group means.
    assert r.value("Parameter estimates", "Intercept", "Estimate") == pytest.approx(np.mean([np.mean(v) for v in PLANT.values()]))


def test_fit_model_rejects_collinear():
    with pytest.raises(AnalysisError):
        regression.fit_model([1, 2, 3, 4, 5], {"a": [1, 2, 3, 4, 5], "b": [2, 4, 6, 8, 10]})


# ----------------------------------------------------------------------------- fit y by x


def test_bivariate_matches_linregress():
    rng = np.random.default_rng(1)
    x = rng.normal(size=40)
    y = 2 + 3 * x + rng.normal(size=40)
    r = bivariate.fit_y_by_x(y.tolist(), x.tolist(), "y", "x")
    lr = stats.linregress(x, y)
    assert r.analysis == "bivariate"
    assert r.value("Parameter estimates", "x", "Estimate") == pytest.approx(lr.slope)
    assert r.value("Parameter estimates", "x", "Std error") == pytest.approx(lr.stderr)
    assert r.value("Parameter estimates", "Intercept", "Std error") == pytest.approx(lr.intercept_stderr)
    assert r.value("Parameter estimates", "x", "p-value") == pytest.approx(lr.pvalue)
    assert r.value("Summary of fit", "R²", "Value") == pytest.approx(lr.rvalue**2)


def test_oneway_plantgrowth():
    y, g = plant_columns()
    r = bivariate.fit_y_by_x(y, g, "weight", "group")
    assert r.analysis == "oneway"
    assert r.value("Analysis of variance", "group", "F ratio") == pytest.approx(4.846088, rel=1e-6)
    assert r.value("Analysis of variance", "group", "p-value") == pytest.approx(0.01590996, rel=1e-5)
    assert r.value("Means", "trt2", "Mean") == pytest.approx(5.526)
    assert r.value("Tukey HSD comparisons", "trt2 - trt1", "Difference") == pytest.approx(0.865)
    assert r.value("Tukey HSD comparisons", "trt2 - trt1", "Adjusted p-value") == pytest.approx(0.0120064, abs=2e-5)
    assert r.value("Tukey HSD comparisons", "trt1 - ctrl", "Adjusted p-value") == pytest.approx(0.3908711, abs=2e-5)
    assert r.value("Tukey HSD comparisons", "trt2 - ctrl", "Lower 95%") == pytest.approx(-0.1972161, abs=1e-6)
    assert r.value("Tests that the variances are equal", "Bartlett", "Statistic") == pytest.approx(2.8786, abs=1e-4)
    w = r.table("Welch ANOVA (unequal variances)").rows[0]
    assert w[0] == pytest.approx(5.181, abs=1e-3)
    assert w[2] == pytest.approx(17.128, abs=1e-3)
    assert w[3] == pytest.approx(0.01739, abs=1e-5)


def test_contingency_matches_scipy():
    y = ["yes"] * 12 + ["no"] * 8 + ["yes"] * 5 + ["no"] * 15
    x = ["A"] * 20 + ["B"] * 20
    r = bivariate.fit_y_by_x(y, x, "answer", "site")
    assert r.analysis == "contingency"
    chi2 = stats.chi2_contingency([[8, 12], [15, 5]], correction=False)[0]
    assert r.value("Tests", "Pearson chi-square", "Statistic") == pytest.approx(chi2)
    assert r.value("Tests", "Fisher's exact (two-sided)", "p-value") == pytest.approx(stats.fisher_exact([[8, 12], [15, 5]])[1])


def test_numeric_codes_can_be_forced_nominal():
    y, g = plant_columns()
    codes = [{"ctrl": 1, "trt1": 2, "trt2": 3}[v] for v in g]
    r = bivariate.fit_y_by_x(y, codes, "weight", "group", x_type="nominal")
    assert r.analysis == "oneway"
    assert r.value("Means", "3", "Mean") == pytest.approx(5.526)


# ----------------------------------------------------------------------------- distribution


def test_distribution_moments_and_quantiles():
    data = list(range(1, 11)) + [None, "", "n/a"]
    r = distribution.distribution(data, "v")
    assert r.value("Summary statistics", "N", "Value") == 10
    assert r.value("Summary statistics", "Mean", "Value") == pytest.approx(5.5)
    assert r.value("Summary statistics", "Std dev", "Value") == pytest.approx(3.0276503540974917)
    assert r.value("Summary statistics", "Upper 95% mean", "Value") == pytest.approx(5.5 + stats.t.ppf(0.975, 9) * 3.0276503540974917 / math.sqrt(10))
    assert r.value("Quantiles", "50.0% median", "Value") == pytest.approx(5.5)
    assert r.value("Normality tests", "Shapiro-Wilk", "p-value") == pytest.approx(stats.shapiro(range(1, 11)).pvalue)
    assert any("3 missing" in n for n in r.notes)


def test_distribution_needs_two_values():
    with pytest.raises(AnalysisError):
        distribution.distribution([1, None])


# ----------------------------------------------------------------------------- control charts


def test_control_constants():
    assert control.c4(5) == pytest.approx(0.9400, abs=1e-4)
    assert 3 / (control.d2(5) * math.sqrt(5)) == pytest.approx(0.577, abs=1e-3)  # A2
    assert 1 + 3 * control.d3(5) / control.d2(5) == pytest.approx(2.114, abs=1e-3)  # D4
    assert 1 + 3 * control.d3(2) / control.d2(2) == pytest.approx(3.267, abs=1e-3)


def test_imr_limits():
    r = control.imr([10, 12, 11, 13, 12], "t")
    sigma = 1.5 / 1.128
    assert r.value("Control limits", "Individuals of t", "UCL") == pytest.approx(11.6 + 3 * sigma, rel=1e-3)
    assert r.value("Control limits", "Moving range", "UCL") == pytest.approx(1.5 * 3.267, rel=1e-3)


def test_xbar_r_equal_subgroups():
    rng = np.random.default_rng(7)
    data = rng.normal(50, 2, size=100)
    r = control.xbar_r(data.tolist(), size=5, name="d")
    groups = data.reshape(20, 5)
    rbar = np.ptp(groups, axis=1).mean()
    xbb = groups.mean()
    a2 = 3 / (2.326 * math.sqrt(5))
    assert r.value("Control limits", "X̄", "UCL") == pytest.approx(xbb + a2 * rbar, rel=1e-4)
    assert r.value("Control limits", "Range", "UCL") == pytest.approx(rbar * 2.114, rel=1e-3)


def test_xbar_s_with_subgroup_column():
    data = [5, 6, 7, 6, 7, 8, 5, 5, 6]
    sg = ["a", "a", "a", "b", "b", "b", "c", "c", "c"]
    r = control.xbar_s(data, sg, name="d")
    sbar = np.mean([1.0, 1.0, np.std([5, 5, 6], ddof=1)])
    assert r.value("Control limits", "X̄", "Sigma estimate") == pytest.approx(sbar / control.c4(3))


def test_p_chart_variable_limits():
    r = control.p_chart([5, 8, 3], [100, 200, 50])
    assert r.value("Control limits", "p", "Center") == pytest.approx(16 / 350)
    assert r.value("Control limits", "p", "UCL") == "varies"


def test_western_electric_rules():
    z = np.array([0.5] * 8)
    assert control.western_electric(z)[4] == [7]
    z = np.array([0, 0, 3.5])
    assert control.western_electric(z)[1] == [2]
    z = np.array([2.5, 0, 2.5])
    assert control.western_electric(z)[2] == [2]
    z = np.array([-1.5, -1.5, 0, -1.5, -1.5])
    assert control.western_electric(z)[3] == [4]


# ----------------------------------------------------------------------------- api


def test_api_round_trip_is_valid_json():
    y, g = plant_columns()
    req = {
        "analysis": "fit_y_by_x",
        "columns": {"weight": y, "group": g},
        "roles": {"y": ["weight"], "x": ["group"]},
    }
    out = json.loads(cellstat.run_json(json.dumps(req)))
    assert out["ok"]
    assert out["results"][0]["analysis"] == "oneway"


def test_api_reports_user_errors():
    out = cellstat.run({"analysis": "distribution", "columns": {}, "roles": {}})
    assert not out["ok"] and "Y column" in out["error"]
    out = cellstat.run({"analysis": "nope"})
    assert not out["ok"]


def test_api_control_chart():
    out = cellstat.run(
        {"analysis": "control_chart", "columns": {"m": [1, 2, 3, 2, 1, 2]}, "roles": {"y": ["m"]}, "options": {"chart": "imr"}}
    )
    assert out["ok"], out

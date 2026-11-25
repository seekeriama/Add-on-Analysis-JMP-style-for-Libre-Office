"""Data table tools: stack, split, join, update and the rest."""

import json

import pytest

import cellstat
from cellstat import tables
from cellstat.result import AnalysisError


def rows(r, i=0):
    t = r.tables[i]
    return t.columns, t.rows


WIDE = {"ID": ["a", "b", "c"], "Q1": [1.0, 2.0, None], "Q2": [10.0, 20.0, 30.0]}


def test_stack_row_major_and_drop_missing():
    r = tables.stack(WIDE, ["Q1", "Q2"])
    cols, body = rows(r)
    assert cols == ["ID", "Label", "Data"]
    assert body[:3] == [["a", "Q1", 1.0], ["a", "Q2", 10.0], ["b", "Q1", 2.0]]
    assert len(body) == 6
    assert len(rows(tables.stack(WIDE, ["Q1", "Q2"], drop_missing=True))[1]) == 5
    assert r.layout == "data" and r.sheet_name == "Stacked"


def test_stack_name_clash():
    with pytest.raises(AnalysisError):
        tables.stack(WIDE, ["Q1", "Q2"], data_name="ID")


def test_split_undoes_stack():
    long = tables.stack(WIDE, ["Q1", "Q2"])
    c, b = rows(long)
    cols = {n: [r[k] for r in b] for k, n in enumerate(c)}
    sc, sb = rows(tables.split(cols, ["Data"], "Label", ["ID"]))
    assert sc == ["ID", "Q1", "Q2"]
    assert sb == [["a", 1.0, 10.0], ["b", 2.0, 20.0], ["c", None, 30.0]]


def test_split_without_group_and_numeric_labels():
    cols = {"y": [1, 2, 3, 4], "t": [2, 1, 2, 1]}
    c, b = rows(tables.split(cols, ["y"], "t"))
    assert c == ["1", "2"]
    assert b == [[2, 1], [4, 3]]


def test_transpose_with_labels():
    c, b = rows(tables.transpose({"name": ["x", "y"], "v1": [1, 2], "v2": [3, 4]}, label="name"))
    assert c == ["name", "x", "y"]
    assert b == [["v1", 1, 2], ["v2", 3, 4]]


def test_sort_multiple_keys_missing_last():
    t = {"g": ["b", "a", "b", None, "a"], "v": [1, 5, 3, 9, 2]}
    _, b = rows(tables.sort(t, [("g", False), ("v", True)]))
    assert b == [["a", 5], ["a", 2], ["b", 3], ["b", 1], [None, 9]]
    _, b = rows(tables.sort({"x": ["10", 9, "apple", 2.5]}, [("x", False)]))
    assert [r[0] for r in b] == [2.5, 9, "10", "apple"]


def test_summary_by_group():
    t = {"g": ["a", "b", "a", "b", "a"], "v": [1, 2, 3, None, 5]}
    c, b = rows(tables.summary(t, ["g"], ["v"], ["n", "mean", "n_missing", "sum"]))
    assert c == ["g", "N Rows", "N(v)", "Mean(v)", "N Missing(v)", "Sum(v)"]
    assert b == [["a", 3, 3, 3.0, 0, 9.0], ["b", 2, 1, 2.0, 1, 2.0]]


def test_subset_condition_and_sample():
    t = {"x": [1, 5, 10, None], "s": ["Apple", "pear", "apple pie", "x"]}
    _, b = rows(tables.subset(t, where="x", op="ge", value="5"))
    assert [r[0] for r in b] == [5, 10]
    _, b = rows(tables.subset(t, ["s"], where="s", op="contains", value="APPLE"))
    assert b == [["Apple"], ["apple pie"]]
    _, b = rows(tables.subset(t, where="x", op="missing"))
    assert b == [[None, "x"]]
    r1 = tables.subset(t, sample="random_n", count=2, seed=7)
    r2 = tables.subset(t, sample="random_n", count=2, seed=7)
    assert rows(r1)[1] == rows(r2)[1] and len(rows(r1)[1]) == 2
    with pytest.raises(AnalysisError):
        tables.subset(t, where="x", op="eq")


LEFT = {"id": [1.0, 2.0, 3.0], "name": ["ann", "bob", "cy"]}
RIGHT = {"id": ["2", "3", "4", "3"], "score": [20, 30, 40, 31], "name": ["B", "C", "D", "C2"]}


def test_join_kinds():
    c, b = rows(tables.join(LEFT, RIGHT, ["id"], how="inner"))
    assert c == ["id", "name", "score", "name (B)"]
    assert b == [[2.0, "bob", 20, "B"], [3.0, "cy", 30, "C"], [3.0, "cy", 31, "C2"]]
    assert len(rows(tables.join(LEFT, RIGHT, ["id"], how="left"))[1]) == 4
    _, b = rows(tables.join(LEFT, RIGHT, ["id"], how="outer"))
    assert b[-1] == ["4", None, 40, "D"]
    _, b = rows(tables.join(LEFT, RIGHT, how="row"))
    assert len(b) == 4 and b[3][:2] == [None, None]


def test_join_different_key_names():
    b2 = {"key": [1, 2], "z": ["p", "q"]}
    c, b = rows(tables.join(LEFT, b2, ["id"], ["key"]))
    assert c == ["id", "name", "z"] and b == [[1.0, "ann", "p"], [2.0, "bob", "q"]]
    with pytest.raises(AnalysisError):
        tables.join(LEFT, b2, ["id"])


def test_update():
    a = {"id": [1, 2, 3], "v": [10, 20, 30], "w": ["x", "y", "z"]}
    b = {"id": [3, 1, 9], "v": [33, None, 99], "extra": ["e3", "e1", "e9"]}
    r = tables.update(a, b, ["id"])
    c, body = rows(r)
    assert c == ["id", "v", "w"]
    assert body == [[1, 10, "x"], [2, 20, "y"], [3, 33, "z"]]
    _, body = rows(tables.update(a, b, ["id"], ignore_missing=False, add_columns=True))
    assert body[0] == [1, None, "x", "e1"]


def test_concatenate():
    a = {"x": [1], "y": ["a"]}
    b = {"y": ["b"], "z": [True]}
    c, body = rows(tables.concatenate(a, b, True, "S1", "S2"))
    assert c == ["x", "y", "z", "Source Table"]
    assert body == [[1, "a", None, "S1"], [None, "b", True, "S2"]]


def test_missing_pattern():
    t = {"a": [1, None, 3, None], "b": [1, 2, None, 4]}
    r = tables.missing_pattern(t)
    c, b = rows(r)
    assert c == ["Count", "Number of columns missing", "Pattern", "a", "b"]
    assert b[0] == [2, 1, "10", 1, 0]
    assert r.value("Missing values by column", "a", "N Missing") == 2
    assert r.layout == "report"


def test_compare_by_row_and_key():
    a = {"id": [1, 2, 3], "v": [1.0, 2.0, 3.0], "only_a": [0, 0, 0]}
    b = {"id": [1, 2, 4], "v": [1.0, 2.5, 4.0]}
    r = tables.compare(a, b)
    assert r.value("Overview", "Cells that differ", "First table") == 3  # id 3≠4, v 2≠2.5, 3≠4
    r = tables.compare(a, b, ["id"])
    assert r.table("Cell differences").rows == [["2", "v", 2.0, 2.5]]
    assert r.value("Overview", "Rows without a match", "First table") == 1
    assert r.value("Columns", "only_a", "In second") == "No"
    same = tables.compare(a, dict(a))
    assert same.notes[0] == "The tables hold the same data."


def test_anonymize():
    t = {"name": ["ann", "bob", "ann"], "age": [30, 40, None], "keep": ["k", "k", "k"]}
    out = tables.anonymize(t, ["name", "age"], seed=1, include_key=True)
    c, b = rows(out[0])
    assert c == ["C1", "C2", "keep"]
    assert b[0][0] == b[2][0] != b[1][0] and b[0][0].startswith("C1 ")
    assert b[2][1] is None
    # A linear rescale keeps differences proportional.
    scale = float(out[1].tables[0].rows[-1][3].split()[0])
    assert (b[1][1] - b[0][1]) / 10 == pytest.approx(scale)
    assert out[1].sheet_name == "Anonymization key"
    assert tables.anonymize(t, ["name"], rename=False, seed=2)[0].tables[0].columns == ["name", "age", "keep"]


def test_api_round_trip():
    req = {"analysis": "stack", "columns": WIDE, "roles": {"stack": ["Q1", "Q2"]}, "options": {}}
    res = json.loads(cellstat.run_json(json.dumps(req)))
    assert res["ok"] and res["results"][0]["layout"] == "data"
    req = {"analysis": "join", "columns": LEFT, "roles": {"key": ["id"]}, "options": {"how": "left"}}
    res = cellstat.run(req)
    assert not res["ok"] and "second table" in res["error"]
    req["columns_b"] = RIGHT
    assert len(cellstat.run(req)["results"][0]["tables"][0]["rows"]) == 4
    req = {"analysis": "sort", "columns": LEFT, "roles": {"by": ["name"]}, "options": {"desc": True}}
    assert cellstat.run(req)["results"][0]["tables"][0]["rows"][0][1] == "cy"

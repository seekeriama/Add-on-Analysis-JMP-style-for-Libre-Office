"""Data table tools: reshape, combine and clean tables.

Every function takes whole columns (``{name: [cells]}``) and returns a Result
whose first table is the new data table. Results built with ``layout="data"``
are written by the hosts as a plain table at A1 of a new sheet, so the output
can be analysed again straight away. Cell values pass through unchanged:
numbers stay numbers, text stays text, missing cells become empty.
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Any, Sequence

from .data import _is_missing, is_numeric_column, to_float, to_label
from .result import AnalysisError, Result, Table

Columns = dict[str, list[Any]]


# --------------------------------------------------------------------- helpers


def _nrows(cols: Columns) -> int:
    lengths = {len(v) for v in cols.values()}
    if len(lengths) > 1:
        raise AnalysisError("All columns of a table must have the same number of rows.")
    return lengths.pop() if lengths else 0


def _need(cols: Columns, names: Sequence[str], table: str = "the table") -> None:
    for n in names:
        if n not in cols:
            raise AnalysisError(f"Column '{n}' is not in {table}.")


def _rows(cols: Columns) -> list[list[Any]]:
    names = list(cols)
    return [[cols[c][i] for c in names] for i in range(_nrows(cols))]


def _data_result(analysis: str, title: str, sheet: str, columns: list[str], rows: list[list[Any]], notes=None) -> Result:
    r = Result(analysis, title, [Table(title, columns, rows)], notes=list(notes or []))
    r.layout = "data"
    r.sheet_name = sheet
    return r


def _match_key(v: Any) -> str | None:
    """Value used to match rows across tables: 1, 1.0 and "1" all match."""
    if _is_missing(v):
        return None
    if isinstance(v, bool):
        return str(v)
    f = to_float(v)
    if not math.isnan(f) and not isinstance(v, str):
        return repr(float(f))
    if isinstance(v, str):
        s = v.strip()
        try:
            return repr(float(s))
        except ValueError:
            return s
    return to_label(v)


def _sort_key(v: Any):
    """Numbers before text (numerically), text case-insensitively."""
    if isinstance(v, bool):
        return (0, float(v), "")
    f = to_float(v)
    if not math.isnan(f):
        return (0, f, "")
    s = str(v)
    return (1, 0.0, s.lower() + "\0" + s)


def _unique(name: str, used: set[str]) -> str:
    base, k = name, 2
    while name in used:
        name, k = f"{base} ({k})", k + 1
    used.add(name)
    return name


def _label(v: Any, fallback: str) -> str:
    s = to_label(v)
    return fallback if s is None else s


def _cells_equal(a: Any, b: Any) -> bool:
    if _is_missing(a) and _is_missing(b):
        return True
    if _is_missing(a) or _is_missing(b):
        return False
    fa, fb = to_float(a), to_float(b)
    if not math.isnan(fa) and not math.isnan(fb) and not isinstance(a, str) and not isinstance(b, str):
        return fa == fb or math.isclose(fa, fb, rel_tol=1e-12, abs_tol=0.0)
    return to_label(a) == to_label(b)


def _key_pairs(a: Columns, b: Columns, keys_a: Sequence[str], keys_b: Sequence[str] | None) -> list[tuple[str, str]]:
    if not keys_a:
        raise AnalysisError("Choose at least one column to match rows on.")
    keys_b = list(keys_b or [])
    if not keys_b:
        missing = [k for k in keys_a if k not in b]
        if missing:
            raise AnalysisError(
                f"The second table has no column named {', '.join(repr(m) for m in missing)}. "
                "Choose the matching columns of the second table."
            )
        keys_b = list(keys_a)
    if len(keys_b) != len(keys_a):
        raise AnalysisError("Choose the same number of matching columns in both tables.")
    _need(a, keys_a, "the first table")
    _need(b, keys_b, "the second table")
    return list(zip(keys_a, keys_b))


def _row_keys(cols: Columns, names: Sequence[str]) -> list[tuple | None]:
    n = _nrows(cols)
    out = []
    for i in range(n):
        k = tuple(_match_key(cols[c][i]) for c in names)
        out.append(None if any(v is None for v in k) else k)
    return out


# ----------------------------------------------------------------------- summary

STATS = {
    "n": ("N", lambda xs, raw: len(xs)),
    "n_missing": ("N Missing", lambda xs, raw: len(raw) - len(xs)),
    "mean": ("Mean", lambda xs, raw: statistics.fmean(xs) if xs else None),
    "std": ("Std Dev", lambda xs, raw: statistics.stdev(xs) if len(xs) > 1 else None),
    "min": ("Min", lambda xs, raw: min(xs) if xs else None),
    "max": ("Max", lambda xs, raw: max(xs) if xs else None),
    "sum": ("Sum", lambda xs, raw: math.fsum(xs)),
    "median": ("Median", lambda xs, raw: statistics.median(xs) if xs else None),
}


def summary(cols: Columns, group: Sequence[str] = (), values: Sequence[str] = (), stats: Sequence[str] = ("n", "mean", "std", "min", "max")) -> Result:
    """One row per combination of the group columns, with statistics of the value columns."""
    group, values = list(group), list(values)
    _need(cols, group + values)
    stats = [s for s in stats if s in STATS] or ["mean"]
    if not group and not values:
        raise AnalysisError("Choose group columns, statistics columns, or both.")
    n = _nrows(cols)
    order: dict[tuple, list[int]] = {}
    first: dict[tuple, list[Any]] = {}
    for i in range(n):
        k = tuple(_match_key(cols[g][i]) for g in group)
        if k not in order:
            order[k] = []
            first[k] = [cols[g][i] for g in group]
        order[k].append(i)
    keys = sorted(order, key=lambda k: [(1, (0, 0.0, "")) if v is None else (0, _sort_key(first[k][j])) for j, v in enumerate(k)])
    names = group + ["N Rows"] + [f"{STATS[s][0]}({v})" for v in values for s in stats]
    rows = []
    for k in keys:
        idx = order[k]
        row = [None if v is None else first[k][j] for j, v in enumerate(k)] + [len(idx)]
        for v in values:
            raw = [cols[v][i] for i in idx]
            xs = [x for x in (to_float(c) for c in raw) if not math.isnan(x)]
            row += [STATS[s][1](xs, raw) for s in stats]
        rows.append(row)
    return _data_result("summary", "Summary", "Summary", names, rows)


# ------------------------------------------------------------------------ subset

OPS = {
    "eq": "equals",
    "ne": "does not equal",
    "lt": "is less than",
    "le": "is at most",
    "gt": "is greater than",
    "ge": "is at least",
    "contains": "contains",
    "not_contains": "does not contain",
    "missing": "is missing",
    "not_missing": "is not missing",
}


def _test(v: Any, op: str, target: Any) -> bool:
    if op == "missing":
        return _is_missing(v)
    if op == "not_missing":
        return not _is_missing(v)
    if _is_missing(v):
        return op == "ne"
    t = "" if target is None else str(target).strip()
    if op in ("contains", "not_contains"):
        hit = t.lower() in str(to_label(v)).lower()
        return hit if op == "contains" else not hit
    fv, ft = to_float(v), to_float(t)
    if not math.isnan(fv) and not math.isnan(ft):
        a, b = fv, ft
    else:
        a, b = str(to_label(v)).lower(), t.lower()
        if op in ("lt", "le", "gt", "ge") and (not math.isnan(fv) or not math.isnan(ft)):
            a, b = _sort_key(v), _sort_key(t)
    return {"eq": a == b, "ne": a != b, "lt": a < b, "le": a <= b, "gt": a > b, "ge": a >= b}[op]


def subset(cols: Columns, keep: Sequence[str] = (), where: str | None = None, op: str = "eq", value: Any = None,
           sample: str = "all", count: int | None = None, fraction: float | None = None, seed: int | None = None) -> Result:
    """Rows matching a condition and/or a sample of rows, with chosen columns."""
    keep = list(keep) or list(cols)
    _need(cols, keep)
    n = _nrows(cols)
    idx = list(range(n))
    notes = []
    if where:
        _need(cols, [where])
        if op not in OPS:
            raise AnalysisError(f"Unknown condition '{op}'.")
        if op not in ("missing", "not_missing") and (value is None or str(value).strip() == ""):
            raise AnalysisError("Type a value for the row condition.")
        idx = [i for i in idx if _test(cols[where][i], op, value)]
        tail = "" if op in ("missing", "not_missing") else f" {value}"
        notes.append(f"Rows where {where} {OPS[op]}{tail}: {len(idx)} of {n}.")
    if sample != "all":
        if sample in ("random_n", "first_n"):
            if not count or count < 1:
                raise AnalysisError("Enter how many rows to keep.")
            k = min(int(count), len(idx))
        elif sample == "random_fraction":
            if fraction is None or not 0 < fraction <= 1:
                raise AnalysisError("Enter a fraction between 0 and 1.")
            k = round(len(idx) * fraction)
        else:
            raise AnalysisError(f"Unknown sampling method '{sample}'.")
        if sample == "first_n":
            idx = idx[:k]
        else:
            idx = sorted(random.Random(seed).sample(idx, k))
            notes.append(f"Random sample of {k} rows" + (f" (seed {seed})." if seed is not None else "."))
    rows = [[cols[c][i] for c in keep] for i in idx]
    return _data_result("subset", "Subset", "Subset", keep, rows, notes)


# -------------------------------------------------------------------------- sort


def sort(cols: Columns, by: Sequence[tuple[str, bool]]) -> Result:
    """Rows ordered by one or more columns; ``by`` is [(column, descending)]. Missing values go last."""
    by = [(c, d) for c, d in by if c]
    if not by:
        raise AnalysisError("Choose a column to sort by.")
    _need(cols, [c for c, _ in by])
    idx = list(range(_nrows(cols)))
    for c, desc in reversed(by):  # stable sorts, least significant first
        present = [i for i in idx if not _is_missing(cols[c][i])]
        absent = [i for i in idx if _is_missing(cols[c][i])]
        present.sort(key=lambda i: _sort_key(cols[c][i]), reverse=desc)
        idx = present + absent
    names = list(cols)
    rows = [[cols[c][i] for c in names] for i in idx]
    desc = ", ".join(f"{c} ({'descending' if d else 'ascending'})" for c, d in by)
    return _data_result("sort", "Sorted", "Sorted", names, rows, [f"Sorted by {desc}."])


# ------------------------------------------------------------------------- stack


def stack(cols: Columns, stack_cols: Sequence[str], data_name: str = "Data", label_name: str = "Label", drop_missing: bool = False) -> Result:
    """Several columns into one: each row becomes one row per stacked column."""
    stack_cols = list(stack_cols)
    if len(stack_cols) < 2:
        raise AnalysisError("Choose at least two columns to stack.")
    _need(cols, stack_cols)
    data_name = (data_name or "Data").strip()
    label_name = (label_name or "Label").strip()
    others = [c for c in cols if c not in stack_cols]
    if data_name == label_name:
        raise AnalysisError("The new data and label columns need different names.")
    for nm in (data_name, label_name):
        if nm in others:
            raise AnalysisError(f"A column named '{nm}' already exists. Choose another name for the new column.")
    rows = []
    for i in range(_nrows(cols)):
        base = [cols[c][i] for c in others]
        for c in stack_cols:
            v = cols[c][i]
            if drop_missing and _is_missing(v):
                continue
            rows.append(base + [c, v])
    return _data_result("stack", "Stacked", "Stacked", others + [label_name, data_name], rows)


# ------------------------------------------------------------------------- split


def split(cols: Columns, split_cols: Sequence[str], by: str, group: Sequence[str] = ()) -> Result:
    """The opposite of stack: values of ``by`` become new columns holding ``split_cols``."""
    split_cols, group = list(split_cols), list(group)
    if not split_cols:
        raise AnalysisError("Choose the column(s) to split.")
    if not by:
        raise AnalysisError("Choose the column whose values become the new column names.")
    _need(cols, split_cols + [by] + group)
    if by in split_cols or by in group:
        raise AnalysisError("The split-by column cannot also be split or used to group rows.")
    n = _nrows(cols)
    labels: dict[str, Any] = {}
    out_rows: dict[tuple, dict] = {}
    seen: dict[tuple, int] = {}
    skipped = 0
    for i in range(n):
        lab = to_label(cols[by][i])
        if lab is None:
            skipped += 1
            continue
        labels.setdefault(lab, cols[by][i])
        g = tuple(_match_key(cols[c][i]) for c in group)
        occ = seen.get((g, lab), 0)
        seen[(g, lab)] = occ + 1
        key = (g, occ)
        if key not in out_rows:
            out_rows[key] = {"group": [cols[c][i] for c in group], "cells": {}}
        for s in split_cols:
            out_rows[key]["cells"][(s, lab)] = cols[s][i]
    labs = sorted(labels, key=lambda l: _sort_key(labels[l]))
    used = set(group)
    new_cols = []
    for s in split_cols:
        for lab in labs:
            nm = lab if len(split_cols) == 1 else f"{s} {lab}"
            new_cols.append(((s, lab), _unique(nm, used)))
    rows = [r["group"] + [r["cells"].get(k) for k, _ in new_cols] for r in out_rows.values()]
    notes = []
    if skipped:
        notes.append(f"{skipped} rows with no {by} value were left out.")
    dropped = [c for c in cols if c not in split_cols + group + [by]]
    if dropped:
        notes.append(f"Columns not used: {', '.join(dropped)}. Add them as group columns to keep them.")
    if not group and n:
        notes.append("No group columns: the first value of each label forms row 1, the second row 2, and so on.")
    return _data_result("split", "Split", "Split", group + [nm for _, nm in new_cols], rows, notes)


# --------------------------------------------------------------------- transpose


def transpose(cols: Columns, columns: Sequence[str] = (), label: str | None = None) -> Result:
    """Rows become columns. Values of ``label`` (if chosen) name the new columns."""
    columns = [c for c in (list(columns) or list(cols)) if c != label]
    _need(cols, columns + ([label] if label else []))
    n = _nrows(cols)
    if n > 16000:
        raise AnalysisError(f"{n} rows would make {n} columns, more than a spreadsheet can hold. Subset the rows first.")
    used: set[str] = set()
    first = _unique(label or "Label", used)
    names = [first] + [_unique(_label(cols[label][i], f"Row {i + 1}") if label else f"Row {i + 1}", used) for i in range(n)]
    rows = [[c] + [cols[c][i] for i in range(n)] for c in columns]
    return _data_result("transpose", "Transposed", "Transposed", names, rows)


# -------------------------------------------------------------------------- join

JOIN_KINDS = {"inner": "matching rows only", "left": "all rows of the first table", "right": "all rows of the second table",
              "outer": "all rows of both tables", "row": "side by side, by row number"}


def join(a: Columns, b: Columns, keys_a: Sequence[str] = (), keys_b: Sequence[str] = (), how: str = "inner") -> Result:
    """Columns of two tables side by side, rows matched on key columns (or by row number)."""
    if how not in JOIN_KINDS:
        raise AnalysisError(f"Unknown join type '{how}'.")
    na, nb = _nrows(a), _nrows(b)
    used = set(a)
    pairs = [] if how == "row" else _key_pairs(a, b, keys_a, keys_b)
    b_key_cols = {kb for _, kb in pairs}
    b_cols = [(c, _unique(c if c not in a else f"{c} (B)", used)) for c in b if c not in b_key_cols]
    names = list(a) + [nm for _, nm in b_cols]

    def row(i: int | None, j: int | None) -> list[Any]:
        left = [a[c][i] for c in a] if i is not None else [None] * len(a)
        if i is None and j is not None:
            for ka, kb in pairs:
                left[list(a).index(ka)] = b[kb][j]
        right = [b[c][j] if j is not None else None for c, _ in b_cols]
        return left + right

    rows = []
    if how == "row":
        rows = [row(i if i < na else None, i if i < nb else None) for i in range(max(na, nb))]
        return _data_result("join", "Joined", "Joined", names, rows, [f"Joined {na} and {nb} rows by row number."])

    ka = _row_keys(a, [p[0] for p in pairs])
    kb = _row_keys(b, [p[1] for p in pairs])
    index: dict[tuple, list[int]] = {}
    for j, k in enumerate(kb):
        if k is not None:
            index.setdefault(k, []).append(j)
    matched_b = set()
    matched_a = 0
    for i, k in enumerate(ka):
        hits = index.get(k, []) if k is not None else []
        if hits:
            matched_a += 1
            for j in hits:
                rows.append(row(i, j))
                matched_b.add(j)
        elif how in ("left", "outer"):
            rows.append(row(i, None))
    if how in ("right", "outer"):
        rows += [row(None, j) for j in range(nb) if j not in matched_b]
    on = ", ".join(x if x == y else f"{x} = {y}" for x, y in pairs)
    notes = [f"Matched on {on}; kept {JOIN_KINDS[how]}.",
             f"{matched_a} of {na} rows of the first table and {len(matched_b)} of {nb} rows of the second table found a match."]
    if any(len(v) > 1 for v in index.values()):
        notes.append("Some keys appear more than once in the second table, so matching rows were repeated.")
    return _data_result("join", "Joined", "Joined", names, rows, notes)


# ------------------------------------------------------------------------ update


def update(a: Columns, b: Columns, keys_a: Sequence[str] = (), keys_b: Sequence[str] = (), by_row: bool = False,
           ignore_missing: bool = True, add_columns: bool = False) -> Result:
    """The first table with values replaced from matching rows of the second (columns matched by name)."""
    na, nb = _nrows(a), _nrows(b)
    pairs = [] if by_row else _key_pairs(a, b, keys_a, keys_b)
    keyb = {kb for _, kb in pairs}
    keya = {ka for ka, _ in pairs}
    shared = [c for c in b if c in a and c not in keyb and c not in keya]
    extra = [c for c in b if c not in a and c not in keyb] if add_columns else []
    if not shared and not extra:
        raise AnalysisError("The second table has no columns with the same names as the first. "
                            "Tick 'Add new columns' to bring its columns across.")
    if by_row:
        match = [i if i < nb else None for i in range(na)]
    else:
        last: dict[tuple, int] = {}
        for j, k in enumerate(_row_keys(b, [p[1] for p in pairs])):
            if k is not None:
                last[k] = j
        match = [last.get(k) if k is not None else None for k in _row_keys(a, [p[0] for p in pairs])]
    names = list(a) + extra
    rows, changed, touched = [], 0, 0
    for i in range(na):
        r = [a[c][i] for c in a] + [None] * len(extra)
        j = match[i]
        if j is not None:
            hit = False
            for c in shared:
                v = b[c][j]
                if ignore_missing and _is_missing(v):
                    continue
                pos = names.index(c)
                if not _cells_equal(r[pos], v):
                    r[pos] = v
                    changed += 1
                    hit = True
            for c in extra:
                r[names.index(c)] = b[c][j]
            touched += hit
        rows.append(r)
    notes = [f"{sum(m is not None for m in match)} of {na} rows matched; {changed} cells changed in {touched} rows.",
             f"Columns updated: {', '.join(shared) if shared else 'none'}."]
    if extra:
        notes.append(f"Columns added: {', '.join(extra)}.")
    return _data_result("update", "Updated", "Updated", names, rows, notes)


# ------------------------------------------------------------------- concatenate


def concatenate(a: Columns, b: Columns, source_column: bool = False, source_a: str = "Table 1", source_b: str = "Table 2") -> Result:
    """Rows of the second table below the first; columns matched by name, new ones added."""
    na, nb = _nrows(a), _nrows(b)
    names = list(a) + [c for c in b if c not in a]
    rows = [[a[c][i] if c in a else None for c in names] for i in range(na)]
    rows += [[b[c][j] if c in b else None for c in names] for j in range(nb)]
    if source_column:
        nm = _unique("Source Table", set(names))
        names.append(nm)
        for i, r in enumerate(rows):
            r.append(source_a if i < na else source_b)
    only_a = [c for c in a if c not in b]
    only_b = [c for c in b if c not in a]
    notes = [f"{na} + {nb} = {na + nb} rows."]
    if only_a or only_b:
        notes.append("Columns found in only one table are left empty for the other table's rows: "
                     + ", ".join(only_a + only_b) + ".")
    return _data_result("concatenate", "Concatenated", "Concatenated", names, rows, notes)


# ---------------------------------------------------------- missing data pattern


def missing_pattern(cols: Columns, columns: Sequence[str] = ()) -> Result:
    """How often each combination of missing columns occurs."""
    columns = list(columns) or list(cols)
    _need(cols, columns)
    n = _nrows(cols)
    counts: dict[str, int] = {}
    for i in range(n):
        p = "".join("1" if _is_missing(cols[c][i]) else "0" for c in columns)
        counts[p] = counts.get(p, 0) + 1
    pats = sorted(counts, key=lambda p: (-counts[p], p))
    rows = [[counts[p], p.count("1"), p] + [int(ch) for ch in p] for p in pats]
    per_col = []
    for c in columns:
        m = sum(_is_missing(v) for v in cols[c])
        per_col.append([c, m, 100.0 * m / n if n else None])
    r = Result(
        "missing_pattern", "Missing data pattern",
        [Table("Patterns", ["Count", "Number of columns missing", "Pattern"] + columns, rows),
         Table("Missing values by column", ["Column", "N Missing", "% Missing"], per_col)],
        notes=[f"{counts.get('0' * len(columns), 0)} of {n} rows are complete. In a pattern, 1 marks a missing value."],
    )
    r.sheet_name = "Missing pattern"
    return r


# ----------------------------------------------------------------------- compare

MAX_DIFFS = 1000


def _kind(values: list[Any]) -> str:
    present = [v for v in values if not _is_missing(v)]
    if not present:
        return "Empty"
    return "Numeric" if is_numeric_column(present, 1.0) else "Text"


def compare(a: Columns, b: Columns, keys_a: Sequence[str] = (), keys_b: Sequence[str] = (), source_a: str = "Table 1", source_b: str = "Table 2") -> Result:
    """Differences between two tables: columns, rows and cell values."""
    na, nb = _nrows(a), _nrows(b)
    pairs = _key_pairs(a, b, keys_a, keys_b) if keys_a else []
    common = [c for c in a if c in b and c not in {p[0] for p in pairs}]
    if pairs:
        ka = _row_keys(a, [p[0] for p in pairs])
        kb = _row_keys(b, [p[1] for p in pairs])
        first_b: dict[tuple, int] = {}
        for j, k in enumerate(kb):
            if k is not None:
                first_b.setdefault(k, j)
        keyset_a = {k for k in ka if k is not None}
        matches = [(i, first_b[k]) for i, k in enumerate(ka) if k is not None and k in first_b]
        only_a = [i for i, k in enumerate(ka) if k is None or k not in first_b]
        only_b = [j for j, k in enumerate(kb) if k is None or k not in keyset_a]

        def row_id(i, j):
            src = a if i is not None else b
            r = i if i is not None else j
            names = [p[0] for p in pairs] if i is not None else [p[1] for p in pairs]
            return ", ".join(str(_label(src[c][r], "")) for c in names)
    else:
        matches = [(i, i) for i in range(min(na, nb))]
        only_a = list(range(nb, na))
        only_b = list(range(na, nb))

        def row_id(i, j):
            return (i if i is not None else j) + 1

    diffs, per_col = [], {c: 0 for c in common}
    for i, j in matches:
        for c in common:
            if not _cells_equal(a[c][i], b[c][j]):
                per_col[c] += 1
                if len(diffs) < MAX_DIFFS:
                    diffs.append([row_id(i, j), c, a[c][i], b[c][j]])
    total = sum(per_col.values())

    overview = [
        ["Source", source_a, source_b],
        ["Rows", na, nb],
        ["Columns", len(a), len(b)],
        ["Rows without a match", len(only_a), len(only_b)],
        ["Cells that differ", total, total],
    ]
    col_rows = []
    for c in list(a) + [c for c in b if c not in a]:
        in_a, in_b = c in a, c in b
        col_rows.append([c, "Yes" if in_a else "No", "Yes" if in_b else "No",
                         _kind(a[c]) if in_a else "", _kind(b[c]) if in_b else "",
                         per_col.get(c, None)])
    unmatched = [[row_id(i, None), source_a] for i in only_a][:MAX_DIFFS] + [[row_id(None, j), source_b] for j in only_b][:MAX_DIFFS]
    rid = "Key" if pairs else "Row"
    tables = [
        Table("Overview", ["Item", "First table", "Second table"], overview),
        Table("Columns", ["Column", "In first", "In second", "Type in first", "Type in second", "Cells that differ"], col_rows),
        Table("Cell differences", [rid, "Column", "First table", "Second table"], diffs),
    ]
    if unmatched:
        tables.append(Table("Rows without a match", [rid, "Only in"], unmatched))
    same = total == 0 and not only_a and not only_b and set(a) == set(b)
    notes = ["The tables hold the same data." if same else
             f"{total} cells differ in {len(matches)} matched rows" + (f"; first {MAX_DIFFS} listed." if total > MAX_DIFFS else ".")]
    notes.append(f"Rows matched on {', '.join(x if x == y else f'{x} = {y}' for x, y in pairs)}." if pairs else "Rows matched by row number.")
    r = Result("compare", "Compare tables", tables, notes=notes)
    r.sheet_name = "Compare"
    return r


# --------------------------------------------------------------------- anonymize


def anonymize(cols: Columns, columns: Sequence[str] = (), rename: bool = True, numeric: str = "rescale",
              seed: int | None = None, include_key: bool = False) -> list[Result]:
    """Hide identifying values: text becomes coded labels, numbers can be rescaled, names replaced."""
    columns = list(columns) or list(cols)
    _need(cols, columns)
    if numeric not in ("keep", "rescale", "text"):
        raise AnalysisError(f"Unknown option for numeric columns '{numeric}'.")
    rng = random.Random(seed)
    new_names, out, key = {}, {}, []
    for k, c in enumerate(cols, 1):
        new_names[c] = f"C{k}" if rename and c in columns else c
    used: set[str] = set()
    for c in cols:
        new_names[c] = _unique(new_names[c], used)
    for c in cols:
        vals = cols[c]
        nm = new_names[c]
        if c not in columns:
            out[nm] = list(vals)
            continue
        if numeric != "text" and is_numeric_column(vals, 1.0):
            if numeric == "keep":
                out[nm] = list(vals)
                key.append([c, nm, "(numbers)", "unchanged"])
            else:
                scale = rng.uniform(0.5, 2.0) * rng.choice((1, -1))
                xs = [to_float(v) for v in vals if not _is_missing(v)]
                spread = (max(xs) - min(xs)) if xs else 1.0
                offset = round(rng.uniform(-1, 1) * (spread or 1.0), 6)
                out[nm] = [None if _is_missing(v) else to_float(v) * scale + offset for v in vals]
                key.append([c, nm, "x", f"{scale:.12g} × x + {offset:.12g}"])
        else:
            levels = []
            seen = set()
            for v in vals:
                lab = to_label(v)
                if lab is not None and lab not in seen:
                    seen.add(lab)
                    levels.append(lab)
            codes = list(range(1, len(levels) + 1))
            rng.shuffle(codes)
            m = dict(zip(levels, codes))
            prefix = nm
            out[nm] = [None if to_label(v) is None else f"{prefix} {m[to_label(v)]}" for v in vals]
            key += [[c, nm, lab, f"{prefix} {m[lab]}"] for lab in levels]
    names = list(out)
    rows = [[out[c][i] for c in names] for i in range(_nrows(cols))]
    note = ("Rename columns: " + ", ".join(f"{c} → {new_names[c]}" for c in columns if new_names[c] != c) + ".") if rename else ""
    res = [_data_result("anonymize", "Anonymized", "Anonymized", names, rows,
                        ["Export the key only if you need to reverse the change, and keep it separate from the data."] if include_key else [])]
    if include_key:
        kr = Result("anonymize", "Anonymization key", [Table("Key", ["Original column", "New column", "Original value", "New value"], key)],
                    notes=[n for n in [note] if n])
        kr.sheet_name = "Anonymization key"
        res.append(kr)
    return res

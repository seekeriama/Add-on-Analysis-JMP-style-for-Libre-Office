"""Calc side of CellStat: read the selection and write results over UNO.

Kept free of HTTP and component code so it can be tested against a headless
LibreOffice through a UNO socket.
"""

from __future__ import annotations

import math

import uno
from com.sun.star.awt import Point, Size
from com.sun.star.beans import PropertyValue

BOLD = 150.0  # com.sun.star.awt.FontWeight.BOLD
HEADER_FILL = 0xEEF1F5
PX_TO_HMM = 26.4583  # 1 CSS pixel in 1/100 mm


class CalcError(Exception):
    pass


def _prop(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def current_calc(ctx):
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.getCurrentComponent()
    if doc is None or not doc.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
        raise CalcError("Open a Calc spreadsheet and select your data first.")
    return doc


def to_columns(rows, source):
    """First row = names; mirrors web/src/sheet.ts."""
    rows = [list(r) for r in rows]
    if not rows:
        return {"source": source, "columns": {}}
    header, body = rows[0], rows[1:]
    while body and all(v in ("", None) for v in body[-1]):
        body.pop()
    columns, used = {}, set()
    for j, h in enumerate(header):
        name = str(h).strip() if h not in ("", None) else f"Column {j + 1}"
        if isinstance(h, float) and h.is_integer():
            name = str(int(h))
        base, k = name, 2
        while name in used:
            name, k = f"{base} ({k})", k + 1
        used.add(name)
        col = [None if (v == "" or v is None) else v for v in (r[j] if j < len(r) else None for r in body)]
        if all(v is None for v in col) and base == f"Column {j + 1}":
            continue
        columns[name] = col
    return {"source": source, "columns": columns}


def read_selection(doc):
    sel = doc.getCurrentController().getSelection()
    if sel.supportsService("com.sun.star.sheet.SheetCellRanges"):
        raise CalcError("Select one block of cells, not several.")
    if not sel.supportsService("com.sun.star.sheet.SheetCellRange") and not sel.supportsService("com.sun.star.sheet.SheetCell"):
        raise CalcError("Select a range of cells.")
    addr = sel.getRangeAddress()
    if addr.StartColumn == addr.EndColumn and addr.StartRow == addr.EndRow:
        cursor = sel.getSpreadsheet().createCursorByRange(sel)
        cursor.collapseToCurrentRegion()
        sel = cursor
    elif addr.EndRow - addr.StartRow > 100000:
        # Whole columns selected: trim to the used area.
        cursor = sel.getSpreadsheet().createCursor()
        cursor.gotoEndOfUsedArea(False)
        last = cursor.getRangeAddress().EndRow
        sel = sel.getSpreadsheet().getCellRangeByPosition(addr.StartColumn, addr.StartRow, addr.EndColumn, min(addr.EndRow, last))
    data = sel.getDataArray()
    name = sel.AbsoluteName if hasattr(sel, "AbsoluteName") else ""
    return to_columns(data, name.replace("$", ""))


def _unique_sheet_name(doc, base="CellStat"):
    names = set(doc.Sheets.ElementNames)
    i = 1
    while f"{base} {i}" in names:
        i += 1
    return f"{base} {i}"


def _cell_value(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else ""
    return str(v)


def number_format(v):
    """Mirrors numberFormat in web/src/sheet.ts."""
    if not isinstance(v, float) or not math.isfinite(v):
        return None
    if v.is_integer() and abs(v) < 1e15:
        return "0"
    a = abs(v)
    if a != 0 and (a < 1e-4 or a >= 1e9):
        return "0.000E+00"
    return "0.0####"


def _format_key(doc, code, cache):
    if code not in cache:
        from com.sun.star.lang import Locale

        formats = doc.NumberFormats
        loc = Locale("en", "US", "")
        key = formats.queryKey(code, loc, False)
        cache[code] = key if key != -1 else formats.addNew(code, loc)
    return cache[code]


def export_result(ctx, doc, result, chart_svgs):
    """New sheet with the result's tables, then its charts as pictures to the right."""
    name = _unique_sheet_name(doc)
    doc.Sheets.insertNewByName(name, doc.Sheets.Count)
    sheet = doc.Sheets.getByName(name)

    blocks = [("title", [[result["title"]]])]
    blocks += [("note", [[n]]) for n in result.get("notes", [])]
    for t in result.get("tables", []):
        blocks.append(("caption", [[t["title"]]]))
        blocks.append(("header", [t["columns"]]))
        if t["rows"]:
            blocks.append(("body", t["rows"]))

    row, max_col = 0, 0
    fmt_cache = {}
    for kind, values in blocks:
        width = max(len(r) for r in values)
        max_col = max(max_col, width)
        for i, r in enumerate(values):
            for j in range(width):
                v = _cell_value(r[j] if j < len(r) else None)
                cell = sheet.getCellByPosition(j, row + i)
                if isinstance(v, float):
                    cell.setValue(v)
                    if kind == "body":
                        cell.NumberFormat = _format_key(doc, number_format(v), fmt_cache)
                elif v != "":
                    cell.setString(v)
        rng = sheet.getCellRangeByPosition(0, row, width - 1, row + len(values) - 1)
        if kind == "title":
            rng.CharWeight, rng.CharHeight = BOLD, 14.0
        elif kind == "caption":
            rng.CharWeight = BOLD
        elif kind == "header":
            rng.CharWeight, rng.CellBackColor = BOLD, HEADER_FILL
        elif kind == "note":
            rng.CharPosture = uno.Enum("com.sun.star.awt.FontSlant", "ITALIC")
        row += len(values) + (1 if kind == "body" else 0)

    for j in range(max_col):
        sheet.Columns.getByIndex(j).OptimalWidth = True
    # The title and notes are long single cells; keep the first column readable.
    col0 = sheet.Columns.getByIndex(0)
    col0.Width = min(max(col0.Width, 3000), 7000)

    x = sheet.Columns.getByIndex(max_col).Position.X + 600
    y = 300
    smgr = ctx.ServiceManager
    provider = smgr.createInstanceWithContext("com.sun.star.graphic.GraphicProvider", ctx)
    for svg in chart_svgs:
        data = svg.encode("utf-8")
        stream = smgr.createInstanceWithArgumentsAndContext(
            "com.sun.star.io.SequenceInputStream", (uno.ByteSequence(data),), ctx
        )
        graphic = provider.queryGraphic((_prop("InputStream", stream),))
        shape = doc.createInstance("com.sun.star.drawing.GraphicObjectShape")
        sheet.DrawPage.add(shape)
        shape.Graphic = graphic
        w = _svg_dim(svg, "width", 560)
        h = _svg_dim(svg, "height", 340)
        shape.setSize(Size(int(w * PX_TO_HMM), int(h * PX_TO_HMM)))
        shape.setPosition(Point(int(x), int(y)))
        y += int(h * PX_TO_HMM) + 500

    try:
        doc.getCurrentController().setActiveSheet(sheet)
    except Exception:
        pass
    return name


def _svg_dim(svg, attr, default):
    import re

    m = re.search(attr + r"='(\d+(?:\.\d+)?)'", svg[:400])
    return float(m.group(1)) if m else default

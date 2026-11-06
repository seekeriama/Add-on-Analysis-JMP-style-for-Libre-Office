"""Drive a headless LibreOffice over a UNO socket for end-to-end tests.

    soffice --headless --accept="socket,host=127.0.0.1,port=2002;urp;" &
    python3 lo_session.py setup        # new sheet with sample data, opens the panel
    python3 lo_session.py check        # lists sheets, cell text and pictures on the last sheet
"""

import sys
import time

import uno
from com.sun.star.beans import PropertyValue


def connect():
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    for _ in range(60):
        try:
            return resolver.resolve("uno:socket,host=127.0.0.1,port=2002;urp;StarOffice.ComponentContext")
        except Exception:
            time.sleep(1)
    raise SystemExit("LibreOffice did not start")


def prop(n, v):
    p = PropertyValue()
    p.Name, p.Value = n, v
    return p


PLANT = {
    "ctrl": [4.17, 5.58, 5.18, 6.11, 4.50, 4.61, 5.17, 4.53, 5.33, 5.14],
    "trt1": [4.81, 4.17, 4.41, 3.59, 5.87, 3.83, 6.03, 4.89, 4.32, 4.69],
    "trt2": [6.31, 5.12, 5.54, 5.50, 5.37, 5.29, 4.92, 6.15, 5.80, 5.26],
}


def setup(ctx):
    smgr = ctx.ServiceManager
    desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL("private:factory/scalc", "_blank", 0, (prop("Hidden", False),))
    sheet = doc.Sheets.getByIndex(0)
    rows = [("weight", "group", "batch")]
    i = 0
    for g, vals in PLANT.items():
        for v in vals:
            rows.append((v, g, float(i % 5 + 1)))
            i += 1
    sheet.getCellRangeByPosition(0, 0, 2, len(rows) - 1).setDataArray(tuple(rows))
    doc.getCurrentController().select(sheet.getCellByPosition(0, 0))
    disp = smgr.createInstanceWithContext("com.sun.star.frame.DispatchHelper", ctx)
    disp.executeDispatch(doc.getCurrentController().getFrame(), "service:org.cellstat.calc.Panel?open", "", 0, ())
    print("setup done")


def check(ctx):
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.getCurrentComponent()
    names = doc.Sheets.ElementNames
    print("sheets:", names)
    sheet = doc.Sheets.getByIndex(len(names) - 1)
    for r in range(0, 14):
        vals = [sheet.getCellByPosition(c, r).getString() for c in range(6)]
        print(r + 1, " | ".join(vals))
    print("pictures:", sheet.DrawPage.Count)
    if len(sys.argv) > 2:
        out = sys.argv[2]
        doc.storeToURL(uno.systemPathToFileUrl(out), (prop("FilterName", "calc_pdf_Export"),))
        print("pdf:", out)


if __name__ == "__main__":
    ctx = connect()
    {"setup": setup, "check": check}[sys.argv[1]](ctx)

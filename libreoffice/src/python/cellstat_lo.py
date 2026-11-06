"""CellStat UNO component: menu entry that opens the analysis panel.

The panel is the same web UI as the Excel add-in. LibreOffice has no embedded
browser for extensions, so this component serves the panel from 127.0.0.1 and
opens it in the default browser. Every API call must carry a random token that
only the opened page knows; the server never listens on other interfaces.
"""

import json
import os
import secrets
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import uno
import unohelper
from com.sun.star.task import XJobExecutor

IMPLEMENTATION = "org.cellstat.calc.Panel"
EXTENSION_ID = "org.cellstat.calc"

_server = None
_lock = threading.Lock()


def _extension_dir(ctx):
    try:
        pip = ctx.getByName("/singletons/com.sun.star.deployment.PackageInformationProvider")
        return uno.fileUrlToSystemPath(pip.getPackageLocation(EXTENSION_ID))
    except Exception:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Server:
    def __init__(self, ctx):
        self.ctx = ctx
        self.token = secrets.token_urlsafe(24)
        self.web = os.path.join(_extension_dir(ctx), "web")
        self.doc = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)

            def _authorised(self):
                if not secrets.compare_digest(self.headers.get("X-CellStat-Token", ""), outer.token):
                    self._send(403, {"error": "This page is not connected to LibreOffice. Reopen it from the CellStat menu."})
                    return False
                return True

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path == "/api/selection":
                    if self._authorised():
                        outer.handle(self, outer.selection)
                    return
                files = {"/": ("index.html", "text/html; charset=utf-8"), "/panel.js": ("panel.js", "text/javascript"),
                         "/style.css": ("style.css", "text/css"), "/icon-32.png": ("icon-32.png", "image/png")}
                if path not in files:
                    self._send(404, {"error": "not found"})
                    return
                name, ctype = files[path]
                with open(os.path.join(outer.web, name), "rb") as f:
                    self._send(200, f.read(), ctype)

            def do_POST(self):
                if not self._authorised():
                    return
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n) or b"{}")
                path = self.path.split("?", 1)[0]
                if path == "/api/run":
                    outer.handle(self, lambda: outer.run(body))
                elif path == "/api/export":
                    outer.handle(self, lambda: outer.export(body))
                else:
                    self._send(404, {"error": "not found"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/?token={self.token}"

    def handle(self, handler, fn):
        try:
            handler._send(200, fn())
        except Exception as e:  # shown in the panel
            from cellstat_calc import CalcError

            msg = str(e) if isinstance(e, CalcError) else f"{type(e).__name__}: {e}"
            if not isinstance(e, CalcError):
                traceback.print_exc()
            handler._send(400, {"error": msg})

    def selection(self):
        import cellstat_calc

        self.doc = cellstat_calc.current_calc(self.ctx)
        return cellstat_calc.read_selection(self.doc)

    def run(self, request):
        try:
            import cellstat
        except ImportError as e:
            return {"ok": False, "error": f"CellStat needs NumPy and SciPy in LibreOffice's Python ({sys.executable}): {e}. "
                    "On Debian/Ubuntu: sudo apt install python3-numpy python3-scipy python3-sklearn"}
        return cellstat.run(request)

    def export(self, body):
        import cellstat_calc

        doc = self.doc or cellstat_calc.current_calc(self.ctx)
        return {"sheet": cellstat_calc.export_result(self.ctx, doc, body["result"], body.get("charts", []))}


def get_server(ctx):
    global _server
    with _lock:
        if _server is None:
            _server = _Server(ctx)
        return _server


class PanelJob(unohelper.Base, XJobExecutor):
    def __init__(self, ctx):
        self.ctx = ctx

    def trigger(self, arg):
        if arg == "about":
            self._message("CellStat 0.1", "Statistical analysis for LibreOffice Calc and Excel.\nMIT License.")
            return
        server = get_server(self.ctx)
        if os.environ.get("CELLSTAT_NO_BROWSER"):
            print(server.url, flush=True)
            return
        shell = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.system.SystemShellExecute", self.ctx)
        try:
            shell.execute(server.url, "", 1)  # URIS_ONLY
        except Exception:
            self._message("CellStat", f"Open this address in your browser:\n{server.url}")

    def _message(self, title, text):
        try:
            desktop = self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", self.ctx)
            window = desktop.getCurrentFrame().getContainerWindow()
            toolkit = window.getToolkit()
            box = toolkit.createMessageBox(window, uno.Enum("com.sun.star.awt.MessageBoxType", "INFOBOX"), 1, title, text)
            box.execute()
        except Exception:
            print(title, text)


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(PanelJob, IMPLEMENTATION, ("com.sun.star.task.Job",))

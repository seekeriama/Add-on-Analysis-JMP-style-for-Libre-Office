// Web Worker that runs the Python core with Pyodide, off the Excel UI thread.

declare function importScripts(...urls: string[]): void;
declare function loadPyodide(opts: { indexURL: string }): Promise<Pyodide>;

interface Pyodide {
  loadPackage(names: string[]): Promise<void>;
  unpackArchive(buf: ArrayBuffer, format: string, opts?: { extractDir?: string }): void;
  runPython(code: string): unknown;
  globals: { get(name: string): { run_json(s: string): string } };
}

// Pinned Pyodide release; numpy, scipy and scikit-learn come from its package index.
const PYODIDE_VERSION = "0.29.5";
// A self-hosted copy can be used instead by opening the task pane with ?pyodide=<url ending in />.
const INDEX_URL =
  new URL(self.location.href).searchParams.get("pyodide") ?? `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

const ctx = self as unknown as { postMessage(m: unknown): void; onmessage: ((e: MessageEvent) => void) | null };
let ready: Promise<Pyodide> | null = null;
let sklearnLoaded = false;

function init(): Promise<Pyodide> {
  if (!ready) {
    ready = (async () => {
      ctx.postMessage({ status: "Loading the statistics engine (first time only)…" });
      importScripts(`${INDEX_URL}pyodide.js`);
      const py = await loadPyodide({ indexURL: INDEX_URL });
      await py.loadPackage(["numpy", "scipy"]);
      const zip = await (await fetch("cellstat-core.zip")).arrayBuffer();
      py.unpackArchive(zip, "zip", { extractDir: "/home/pyodide/cellstat-core" });
      py.runPython("import sys; sys.path.insert(0, '/home/pyodide/cellstat-core'); import cellstat");
      ctx.postMessage({ status: "Ready" });
      return py;
    })();
  }
  return ready;
}

ctx.onmessage = async (e: MessageEvent) => {
  const msg = e.data as { type: string; id?: number; request?: { analysis: string } };
  if (msg.type === "init") {
    init().catch((err) => ctx.postMessage({ status: `Engine failed to load: ${err}` }));
    return;
  }
  if (msg.type === "run" && msg.id !== undefined) {
    try {
      const py = await init();
      if (msg.request?.analysis === "decision_tree" && !sklearnLoaded) {
        ctx.postMessage({ status: "Loading scikit-learn…" });
        await py.loadPackage(["scikit-learn"]);
        sklearnLoaded = true;
        ctx.postMessage({ status: "Ready" });
      }
      const out = py.globals.get("cellstat").run_json(JSON.stringify(msg.request));
      ctx.postMessage({ id: msg.id, response: JSON.parse(out) });
    } catch (err) {
      ctx.postMessage({ id: msg.id, response: { ok: false, error: String(err) } });
    }
  }
};

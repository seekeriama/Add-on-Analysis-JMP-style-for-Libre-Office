// Runs the real Excel task pane bundle (with Pyodide) against mocked Office.js.
//   node test/excel/run.js <pyodide index url>   (serves dist/excel + this folder on :8765)
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const pyodide = process.argv[2];
const roots = [path.join(__dirname), path.join(__dirname, "../../dist/excel")];
const pyRoot = process.argv[3];
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".zip": "application/zip", ".wasm": "application/wasm", ".json": "application/json", ".whl": "application/zip", ".mjs": "text/javascript" };
const server = http.createServer((req, res) => {
  const p = decodeURIComponent(req.url.split("?")[0]);
  const candidates = p.startsWith("/pyodide/") ? [path.join(pyRoot, p.slice(9))] : roots.map((r) => path.join(r, p));
  const f = candidates.find((c) => fs.existsSync(c) && fs.statSync(c).isFile());
  if (!f) { res.writeHead(404).end(); return; }
  res.writeHead(200, { "Content-Type": types[path.extname(f)] || "application/octet-stream" });
  fs.createReadStream(f).pipe(res);
}).listen(8765, async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 420, height: 900 } });
  page.on("pageerror", (e) => console.log("PAGE ERROR", e.message));
  try {
    await page.goto(`http://127.0.0.1:8765/harness.html?pyodide=${encodeURIComponent(pyodide)}`);
    await page.waitForFunction(() => document.querySelector("[data-status]")?.textContent === "Ready", null, { timeout: 180000 });
    console.log("engine ready");
    await page.click("#read");
    await page.selectOption("#analysis", "fit_y_by_x");
    await page.selectOption("select[data-role=y]", "weight");
    await page.selectOption("select[data-role=x]", "group");
    await page.click("#run");
    await page.waitForFunction(() => document.querySelector(".result") || document.querySelector(".error"), null, { timeout: 60000 });
    if (await page.locator(".error").count()) throw new Error(await page.locator(".error").innerText());
    console.log("result:", await page.locator(".result h2").innerText());
    const f = await page.locator("table.out").nth(1).locator("tbody tr").first().innerText();
    console.log("anova row:", f.replace(/\s+/g, " "));
    await page.screenshot({ path: process.argv[4] || "excel-taskpane.png", fullPage: false });
    await page.click("[data-export='0']");
    await page.waitForFunction(() => document.querySelector("[data-export='0']")?.textContent?.startsWith("Exported"), null, { timeout: 30000 });
    const log = await page.evaluate(() => window.__excel);
    console.log("export:", log.sheets, "writes", log.writes.length, "images", log.images.length, "active", log.active);
    // Decision tree loads scikit-learn on demand.
    await page.selectOption("#analysis", "decision_tree");
    await page.selectOption("select[data-role=y]", "group");
    await page.check("input[data-role=x][value=weight]");
    await page.click("#run");
    await page.waitForFunction(() => document.querySelector(".result") || document.querySelector(".error"), null, { timeout: 120000 });
    if (await page.locator(".error").count()) throw new Error(await page.locator(".error").innerText());
    console.log("tree:", await page.locator(".result h2").innerText());
  } catch (e) {
    console.log("FAIL", e.message);
    process.exitCode = 1;
  }
  await browser.close();
  server.close();
});

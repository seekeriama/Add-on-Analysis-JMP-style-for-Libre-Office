// End-to-end check of the panel against a running LibreOffice:
//   node panel_e2e.js <panel url> <screenshot dir>
// Expects the sample sheet from lo_session.py setup (weight, group, batch).
const { chromium } = require("playwright");
const { execFileSync } = require("node:child_process");
const path = require("node:path");

async function run(page, out, name) {
  await page.click("#run");
  // The click handler marks the panel busy before it awaits the engine; wait for it to finish.
  await page.waitForFunction(() => { const b = document.querySelector("#run"); return b && !b.disabled; });
  const err = await page.locator(".error").count();
  if (err) throw new Error(`${name}: ${await page.locator(".error").innerText()}`);
  const title = await page.locator(".result h2").first().innerText();
  await page.locator("#results").screenshot({ path: `${out}/${name}.png` });
  console.log(`ok ${name}: ${title}`);
}

(async () => {
  const [url, out] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1100, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(url);
  await page.click("#read");
  await page.waitForSelector("input[data-role=y]");

  await page.check("input[data-role=y][value=weight]");
  await run(page, out, "distribution");

  await page.selectOption("#analysis", "fit_y_by_x");
  await page.selectOption("select[data-role=y]", "weight");
  await page.selectOption("select[data-role=x]", "group");
  await run(page, out, "oneway");
  await page.click("[data-export='0']");
  await page.waitForFunction(() => document.querySelector("[data-export='0']")?.textContent?.startsWith("Exported"));
  console.log("export:", await page.locator("[data-export='0']").innerText());

  await page.selectOption("select[data-role=x]", "batch");
  await run(page, out, "bivariate");

  await page.selectOption("#analysis", "fit_model");
  await page.selectOption("select[data-role=y]", "weight");
  await page.check("input[data-role=x][value=group]");
  await page.check("input[data-role=x][value=batch]");
  await run(page, out, "fit_model");

  await page.selectOption("#analysis", "decision_tree");
  await page.selectOption("select[data-role=y]", "group");
  await page.check("input[data-role=x][value=weight]");
  await page.fill("input[data-opt=min_leaf]", "3");
  await page.dispatchEvent("input[data-opt=min_leaf]", "change");
  await run(page, out, "decision_tree");

  await page.selectOption("#analysis", "control_chart");
  await page.selectOption("select[data-role=y]", "weight");
  await run(page, out, "imr");
  await page.selectOption("select[data-opt=chart]", "xbar_r");
  await run(page, out, "xbar_r");

  await page.selectOption("#analysis", "capability");
  await page.selectOption("select[data-role=y]", "weight");
  for (const [k, v] of [["lsl", "3.5"], ["usl", "6.5"], ["target", "5"]]) {
    await page.fill(`input[data-opt=${k}]`, v);
    await page.dispatchEvent(`input[data-opt=${k}]`, "change");
  }
  await run(page, out, "capability");

  await page.selectOption("#analysis", "doe_design");
  await run(page, out, "doe_design");
  await page.click("[data-export='0']");
  await page.waitForFunction(() => document.querySelector("[data-export='0']")?.textContent?.startsWith("Exported"));
  console.log("design export:", await page.locator("[data-export='0']").innerText());

  await page.selectOption("#analysis", "fit_model");
  await page.click("#run");
  console.log("missing-role message:", await page.locator(".error").innerText());

  // ---- Table tools: output is a plain data table on a new sheet.
  const exportFirst = async (label) => {
    await page.click("[data-export='0']");
    await page.waitForFunction(() => /^Exported|failed/.test(document.querySelector("[data-export='0']")?.textContent ?? "") || document.querySelector(".error"));
    if (await page.locator(".error").count()) throw new Error(`${label} export: ${await page.locator(".error").innerText()}`);
    console.log(`${label} export:`, await page.locator("[data-export='0']").innerText());
  };
  const rowsOf = () => page.locator(".result .small.muted").first().innerText();

  await page.selectOption("#analysis", "summary");
  await page.check("input[data-role=group][value=group]");
  await page.check("input[data-role=y][value=weight]");
  await run(page, out, "tables_summary");
  console.log("summary:", await rowsOf());

  await page.selectOption("#analysis", "split");
  await page.check("input[data-role=split][value=weight]");
  await page.selectOption("select[data-role=by]", "group");
  await run(page, out, "tables_split");
  console.log("split:", await rowsOf());
  await exportFirst("split");

  await page.selectOption("#analysis", "sort");
  await page.selectOption("select[data-role=by]", "weight");
  await page.check("input[data-opt=desc]");
  await run(page, out, "tables_sort");
  console.log("sort first row:", (await page.locator("table.out tbody tr").first().innerText()).replace(/\s+/g, " "));

  await page.selectOption("#analysis", "subset");
  await page.selectOption("select[data-role=where]", "group");
  await page.fill("input[data-opt=value]", "trt2");
  await page.dispatchEvent("input[data-opt=value]", "change");
  await run(page, out, "tables_subset");
  console.log("subset:", await rowsOf());

  // Join needs a second table: select it in Calc, then read it.
  await page.selectOption("#analysis", "join");
  execFileSync("python3", [path.join(__dirname, "lo_session.py"), "select", "1"]);
  await page.click("#read-b");
  await page.waitForSelector("input[data-role=key_b]");
  await page.check("input[data-role=key][value=group]");
  await page.selectOption("select[data-opt=how]", "left");
  await run(page, out, "tables_join");
  console.log("join:", await rowsOf(), "|", (await page.locator("table.out thead").innerText()).replace(/\s+/g, " "));
  await exportFirst("join");

  if (errors.length) throw new Error("page errors: " + errors.join("; "));
  await browser.close();
})().catch((e) => {
  console.error("FAIL", e.message);
  process.exit(1);
});

// The analysis panel: pick data and an analysis, explore results, export to a sheet.

import { ANALYSES, type AnalysisSpec, type OptionSpec, runChoices } from "./analyses";
import { renderChart } from "./charts";
import { escapeXml as esc, fmt } from "./format";
import type { AnalysisRequest, Host, ResultData, SheetData } from "./types";

interface Factor {
  name: string;
  low: string;
  high: string;
}

interface State {
  data: SheetData | null;
  dataB: SheetData | null;
  spec: AnalysisSpec;
  roles: Record<string, string[]>;
  options: Record<string, unknown>;
  types: Record<string, string>;
  factors: Factor[];
  results: ResultData[];
  busy: boolean;
  error: string;
  status: string;
}

/** Rows shown per data table in the panel; export always writes all of them. */
const PREVIEW_ROWS = 100;

export function mount(host: Host, root: HTMLElement): void {
  // ?start=tables opens on the Tables tools (the "Tables" menu entry / ribbon button).
  const start = new URLSearchParams(globalThis.location?.search ?? "").get("start");
  const first = (start === "tables" && ANALYSES.find((a) => a.group === "Tables")) || ANALYSES[0];
  const st: State = {
    data: null,
    dataB: null,
    spec: first,
    roles: {},
    options: defaults(first),
    types: {},
    factors: [
      { name: "Temperature", low: "150", high: "200" },
      { name: "Time", low: "10", high: "20" },
      { name: "Pressure", low: "1", high: "3" },
    ],
    results: [],
    busy: false,
    error: "",
    status: "",
  };
  host.onStatus?.((m) => {
    st.status = m;
    const el = root.querySelector<HTMLElement>("[data-status]");
    if (el) el.textContent = m;
  });

  const columnNames = () => (st.data ? Object.keys(st.data.columns) : []);
  const columnNamesB = () => (st.dataB ? Object.keys(st.dataB.columns) : []);
  const visibleRoles = () => st.spec.roles.filter((r) => !r.when || r.when.values.includes(String(st.options[r.when.option])));

  function render(): void {
    const spec = st.spec;
    const groups = [...new Set(ANALYSES.map((a) => a.group))];
    const needsData = spec.needsData !== false;
    root.innerHTML = `
      <header class="bar">
        <strong>CellStat</strong>
        <span class="muted" data-status>${esc(st.status)}</span>
      </header>
      <section class="card">
        <label class="lbl" for="analysis">Analysis</label>
        <select id="analysis">
          ${groups
            .map(
              (g) =>
                `<optgroup label="${esc(g)}">${ANALYSES.filter((a) => a.group === g)
                  .map((a) => `<option value="${a.id}" ${a.id === spec.id ? "selected" : ""}>${esc(a.label)}</option>`)
                  .join("")}</optgroup>`,
            )
            .join("")}
        </select>
        <p class="muted small">${esc(spec.description)}</p>
      </section>
      ${needsData ? dataCard() : factorsCard()}
      ${spec.tables === 2 ? dataCardB() : ""}
      ${needsData && st.data ? rolesCard() : ""}
      ${optionsCard()}
      <section class="actions">
        <button id="run" class="primary" ${st.busy ? "disabled" : ""}>${st.busy ? "Running…" : spec.id === "doe_design" ? "Create design" : spec.tables ? "Make table" : "Run"}</button>
      </section>
      ${st.error ? `<div class="error" role="alert">${esc(st.error)}</div>` : ""}
      <div id="results">${st.results.map(resultHtml).join("")}</div>
    `;
    wire();
  }

  function dataCard(): string {
    const cols = columnNames();
    return `
      <section class="card">
        <div class="row">
          <div>
            <div class="lbl">${st.spec.tables === 2 ? "First table" : "Data"}</div>
            <div class="small">${
              st.data
                ? `${esc(st.data.source)} · ${cols.length} columns · ${st.data.columns[cols[0]]?.length ?? 0} rows`
                : "Select a range with column names in the first row, then press Use selection."
            }</div>
          </div>
          <button id="read">Use selection</button>
        </div>
      </section>`;
  }

  function dataCardB(): string {
    const cols = columnNamesB();
    return `
      <section class="card">
        <div class="row">
          <div>
            <div class="lbl">Second table</div>
            <div class="small">${
              st.dataB
                ? `${esc(st.dataB.source)} · ${cols.length} columns · ${st.dataB.columns[cols[0]]?.length ?? 0} rows`
                : "Select the second table in the sheet (it can be on another sheet), then press Use selection."
            }</div>
          </div>
          <button id="read-b">Use selection</button>
        </div>
      </section>`;
  }

  function rolesCard(): string {
    const roles = visibleRoles();
    if (!roles.length) return "";
    const chosen = new Set(Object.entries(st.roles).filter(([k]) => !st.spec.roles.find((r) => r.key === k)?.table).flatMap(([, v]) => v));
    return `
      <section class="card">
        ${roles
          .map((r) => {
            const cols = r.table === "b" ? columnNamesB() : columnNames();
            const sel = st.roles[r.key] ?? [];
            const control = r.table === "b" && !st.dataB
              ? `<div class="small muted">Choose the second table first.</div>`
              : r.multiple
              ? `<div class="checks">${cols
                  .map(
                    (c) =>
                      `<label class="check"><input type="checkbox" data-role="${r.key}" value="${esc(c)}" ${sel.includes(c) ? "checked" : ""}> ${esc(c)}</label>`,
                  )
                  .join("")}</div>`
              : `<select data-role="${r.key}">
                  <option value="">${r.optional ? "(none)" : "Choose a column"}</option>
                  ${cols.map((c) => `<option value="${esc(c)}" ${sel[0] === c ? "selected" : ""}>${esc(c)}</option>`).join("")}
                </select>`;
            return `<div class="field"><div class="lbl">${esc(r.label)}${r.hint ? ` <span class="muted">(${esc(r.hint)})</span>` : ""}</div>${control}</div>`;
          })
          .join("")}
        ${
          chosen.size && ["fit_y_by_x", "fit_model", "decision_tree"].includes(st.spec.id)
            ? `<details class="field"><summary class="lbl">Column types</summary>
                ${[...chosen]
                  .map(
                    (c) => `<div class="row small"><span>${esc(c)}</span>
                    <select data-type="${esc(c)}">
                      ${["auto", "continuous", "nominal"].map((t) => `<option value="${t}" ${(st.types[c] ?? "auto") === t ? "selected" : ""}>${t === "auto" ? "Detect" : t === "continuous" ? "Numeric" : "Categorical"}</option>`).join("")}
                    </select></div>`,
                  )
                  .join("")}
              </details>`
            : ""
        }
      </section>`;
  }

  function factorsCard(): string {
    return `
      <section class="card">
        <div class="lbl">Factors (2 to 7)</div>
        <table class="factors">
          <thead><tr><th>Name</th><th>Low</th><th>High</th><th></th></tr></thead>
          <tbody>
            ${st.factors
              .map(
                (f, i) => `<tr>
                <td><input data-factor="${i}" data-k="name" value="${esc(f.name)}"></td>
                <td><input data-factor="${i}" data-k="low" value="${esc(f.low)}" inputmode="decimal"></td>
                <td><input data-factor="${i}" data-k="high" value="${esc(f.high)}" inputmode="decimal"></td>
                <td><button class="icon" data-remove="${i}" aria-label="Remove factor">×</button></td></tr>`,
              )
              .join("")}
          </tbody>
        </table>
        <button id="add-factor" ${st.factors.length >= 7 ? "disabled" : ""}>Add factor</button>
      </section>`;
  }

  function optionsCard(): string {
    const visible = st.spec.options.filter((o) => !o.when || o.when.values.includes(String(st.options[o.when.option])));
    if (!visible.length) return "";
    return `<section class="card">${visible.map(optionHtml).join("")}</section>`;
  }

  function optionHtml(o: OptionSpec): string {
    const v = st.options[o.key];
    if (o.type === "checkbox")
      return `<label class="check field"><input type="checkbox" data-opt="${o.key}" ${v ? "checked" : ""}> ${esc(o.label)}</label>`;
    if (o.type === "text")
      return `<div class="field"><label class="lbl">${esc(o.label)}</label><input data-opt="${o.key}" value="${esc(String(v ?? ""))}"></div>`;
    if (o.type === "multi") {
      const on = new Set((v as string[] | null) ?? []);
      return `<div class="field"><div class="lbl">${esc(o.label)}</div><div class="checks">${(o.choices ?? [])
        .map((c) => `<label class="check"><input type="checkbox" data-multi="${o.key}" value="${c.value}" ${on.has(c.value) ? "checked" : ""}> ${esc(c.label)}</label>`)
        .join("")}</div></div>`;
    }
    if (o.type === "select") {
      const choices = st.spec.id === "doe_design" && o.key === "runs" ? runChoices(st.factors.length) : o.choices ?? [];
      return `<div class="field"><label class="lbl">${esc(o.label)}</label><select data-opt="${o.key}">${choices
        .map((c) => `<option value="${c.value}" ${String(v) === c.value ? "selected" : ""}>${esc(c.label)}</option>`)
        .join("")}</select></div>`;
    }
    return `<div class="field"><label class="lbl">${esc(o.label)}</label><input type="number" data-opt="${o.key}" value="${v ?? ""}" ${o.step ? `step="${o.step}"` : 'step="any"'} ${o.min !== undefined ? `min="${o.min}"` : ""} ${o.max !== undefined ? `max="${o.max}"` : ""}></div>`;
  }

  function resultHtml(r: ResultData, ri: number): string {
    const data = r.layout === "data";
    const t0 = r.tables[0];
    const size = data && t0 ? `<p class="small muted">${t0.rows.length} rows × ${t0.columns.length} columns${t0.rows.length > PREVIEW_ROWS ? `. Showing the first ${PREVIEW_ROWS}; export writes every row.` : ""}</p>` : "";
    return `
      <article class="result">
        <div class="row">
          <h2>${esc(r.title)}</h2>
          <button data-export="${ri}">${data ? "Export to new sheet" : "Export to sheet"}</button>
        </div>
        ${size}
        ${r.notes.map((n) => `<p class="note">${esc(n)}</p>`).join("")}
        <div class="charts">${r.charts.map((c) => `<figure class="chart${c.kind === "tree" ? " wide" : ""}">${renderChart(c)}</figure>`).join("")}</div>
        ${r.tables
          .map(
            (t) => `<div class="tablewrap${data ? " data" : ""}"><table class="out">
              ${data ? "" : `<caption>${esc(t.title)}</caption>`}
              <thead><tr>${t.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
              <tbody>${t.rows.length ? "" : `<tr><td colspan="${t.columns.length}" class="muted">None</td></tr>`}${(data ? t.rows.slice(0, PREVIEW_ROWS) : t.rows)
                .map(
                  (row) =>
                    `<tr>${row
                      .map((v, i) => {
                        const alert = /p-value/i.test(t.columns[i] ?? "") && typeof v === "number" && v < 0.05;
                        const shown = data && typeof v !== "number" ? (v === null ? "" : String(v)) : fmt(v, data ? undefined : t.columns[i]);
                        return `<td class="${typeof v === "number" ? "num" : ""}${alert && !data ? " sig" : ""}">${esc(shown)}</td>`;
                      })
                      .join("")}</tr>`,
                )
                .join("")}</tbody></table></div>`,
          )
          .join("")}
      </article>`;
  }

  function wire(): void {
    const q = <T extends Element>(s: string) => root.querySelector<T>(s);
    q<HTMLSelectElement>("#analysis")?.addEventListener("change", (e) => {
      st.spec = ANALYSES.find((a) => a.id === (e.target as HTMLSelectElement).value)!;
      st.options = defaults(st.spec);
      if (st.spec.id === "doe_design") st.options.runs = String(2 ** st.factors.length);
      st.roles = {};
      st.results = [];
      st.error = "";
      render();
    });
    q("#read")?.addEventListener("click", () => readSelection("a"));
    q("#read-b")?.addEventListener("click", () => readSelection("b"));
    root.querySelectorAll<HTMLSelectElement>("select[data-role]").forEach((el) =>
      el.addEventListener("change", () => {
        st.roles[el.dataset.role!] = el.value ? [el.value] : [];
        render();
      }),
    );
    root.querySelectorAll<HTMLInputElement>("input[data-role]").forEach((el) =>
      el.addEventListener("change", () => {
        const k = el.dataset.role!;
        const cur = new Set(st.roles[k] ?? []);
        if (el.checked) cur.add(el.value);
        else cur.delete(el.value);
        const fromB = st.spec.roles.find((r) => r.key === k)?.table === "b";
        st.roles[k] = (fromB ? columnNamesB() : columnNames()).filter((c) => cur.has(c));
        render();
      }),
    );
    root.querySelectorAll<HTMLSelectElement>("select[data-type]").forEach((el) =>
      el.addEventListener("change", () => {
        st.types[el.dataset.type!] = el.value;
      }),
    );
    root.querySelectorAll<HTMLInputElement | HTMLSelectElement>("[data-opt]").forEach((el) =>
      el.addEventListener("change", () => {
        const k = el.dataset.opt!;
        if (el instanceof HTMLInputElement && el.type === "checkbox") st.options[k] = el.checked;
        else if (el instanceof HTMLInputElement && el.type === "number") st.options[k] = el.value === "" ? null : Number(el.value);
        else st.options[k] = el.value;
        const shapesForm = [...st.spec.roles, ...st.spec.options].some((x) => x.when?.option === k);
        if (shapesForm) render();
      }),
    );
    root.querySelectorAll<HTMLInputElement>("input[data-multi]").forEach((el) =>
      el.addEventListener("change", () => {
        const k = el.dataset.multi!;
        const spec = st.spec.options.find((o) => o.key === k);
        const cur = new Set((st.options[k] as string[] | null) ?? []);
        if (el.checked) cur.add(el.value);
        else cur.delete(el.value);
        st.options[k] = (spec?.choices ?? []).map((c) => c.value).filter((c) => cur.has(c));
      }),
    );
    root.querySelectorAll<HTMLInputElement>("input[data-factor]").forEach((el) =>
      el.addEventListener("change", () => {
        const f = st.factors[Number(el.dataset.factor)];
        (f as unknown as Record<string, string>)[el.dataset.k!] = el.value;
      }),
    );
    root.querySelectorAll<HTMLButtonElement>("[data-remove]").forEach((el) =>
      el.addEventListener("click", () => {
        if (st.factors.length <= 2) return;
        st.factors.splice(Number(el.dataset.remove), 1);
        st.options.runs = String(2 ** st.factors.length);
        render();
      }),
    );
    q("#add-factor")?.addEventListener("click", () => {
      st.factors.push({ name: `Factor ${st.factors.length + 1}`, low: "-1", high: "1" });
      st.options.runs = String(2 ** st.factors.length);
      render();
    });
    q("#run")?.addEventListener("click", run);
    root.querySelectorAll<HTMLButtonElement>("[data-export]").forEach((el) =>
      el.addEventListener("click", async () => {
        const r = st.results[Number(el.dataset.export)];
        el.disabled = true;
        el.textContent = "Exporting…";
        try {
          const where = await host.exportResult(r, r.charts.map(renderChart));
          el.textContent = `Exported to ${where}`;
        } catch (e) {
          st.error = `Export failed: ${(e as Error).message}`;
          render();
        }
      }),
    );
  }

  async function readSelection(which: "a" | "b"): Promise<void> {
    st.error = "";
    try {
      const d = await host.readSelection();
      if (which === "a") st.data = d;
      else st.dataB = d;
      const colsA = new Set(columnNames());
      const colsB = new Set(columnNamesB());
      for (const k of Object.keys(st.roles)) {
        const fromB = st.spec.roles.find((r) => r.key === k)?.table === "b";
        st.roles[k] = st.roles[k].filter((c) => (fromB ? colsB : colsA).has(c));
      }
      if (!Object.keys(d.columns).length) st.error = "The selection is empty.";
    } catch (e) {
      st.error = (e as Error).message;
    }
    render();
  }

  async function run(): Promise<void> {
    st.error = "";
    const spec = st.spec;
    const req: AnalysisRequest = { analysis: spec.id, columns: {}, roles: {}, options: { ...st.options } };
    if (spec.id === "doe_design") {
      const factors = st.factors.map((f) => ({ name: f.name.trim(), low: Number(f.low), high: Number(f.high) }));
      if (factors.some((f) => !f.name || !Number.isFinite(f.low) || !Number.isFinite(f.high) || f.low === f.high)) {
        st.error = "Each factor needs a name and two different numeric levels.";
        return render();
      }
      req.options = { ...req.options, factors, runs: Number(st.options.runs) || 2 ** factors.length };
    } else {
      if (!st.data) {
        st.error = "Choose data first: select a range and press Use selection.";
        return render();
      }
      if (spec.tables === 2 && !st.dataB) {
        st.error = "Choose the second table: select it in the sheet and press Use selection under Second table.";
        return render();
      }
      for (const r of visibleRoles()) {
        const cols = st.roles[r.key] ?? [];
        if (!cols.length && !r.optional) {
          st.error = `Choose ${r.multiple ? "at least one column" : "a column"} for "${r.label}".`;
          return render();
        }
        if (cols.length) req.roles[r.key] = cols;
        if (!r.table) for (const c of cols) req.columns[c] = st.data.columns[c];
      }
      if (spec.tables) {
        // Table tools keep every column, so send the whole table(s).
        req.columns = { ...st.data.columns };
        req.options.source_a = st.data.source;
        if (spec.tables === 2 && st.dataB) {
          req.columns_b = { ...st.dataB.columns };
          req.options.source_b = st.dataB.source;
        }
      }
      const types: Record<string, string> = {};
      for (const [c, t] of Object.entries(st.types)) if (t !== "auto" && c in req.columns) types[c] = t;
      req.options.types = types;
      if (req.roles.subgroup) delete req.options.subgroup_size;
    }
    for (const [k, v] of Object.entries(req.options)) if (v === null || v === "") delete req.options[k];
    st.busy = true;
    render();
    try {
      const res = await host.run(req);
      if (res.ok) st.results = res.results;
      else st.error = res.error;
    } catch (e) {
      st.error = (e as Error).message;
    }
    st.busy = false;
    render();
    root.querySelector("#results")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  render();
}

function defaults(spec: AnalysisSpec): Record<string, unknown> {
  const o: Record<string, unknown> = {};
  for (const opt of spec.options) o[opt.key] = opt.default ?? null;
  if (spec.id === "doe_design") o.runs = "8";
  for (const opt of spec.options) if (Array.isArray(opt.default)) o[opt.key] = [...opt.default];
  return o;
}

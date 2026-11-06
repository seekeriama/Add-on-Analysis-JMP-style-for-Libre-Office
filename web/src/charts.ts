// Renders the core's neutral chart specs as standalone SVG strings.
// The same string is shown in the panel and exported as a picture to the sheet,
// so the SVG carries its own fonts and colours (no CSS variables).

import type { ChartData, Series } from "./types";
import { escapeXml as esc, fmt, niceTicks, tick } from "./format";

const PALETTE = ["#2f6fdf", "#e07b00", "#1a9e77", "#c43c8a", "#7a5cc7", "#8a7a00", "#00838f", "#b0413e"];
const INK = "#1f2328";
const QUIET = "#5c6370";
const GRID = "#e3e6ea";
const AXIS = "#9aa1ab";
const ALERT = "#d1242f";
const FONT = "font-family='system-ui, -apple-system, Segoe UI, Roboto, sans-serif'";

const W = 560;
const H = 340;
const M = { l: 62, r: 92, t: 48, b: 48 };

type Scale = (v: number) => number;

interface Frame {
  parts: string[];
  sx: Scale;
  sy: Scale;
  cats: string[] | null;
}

export function renderChart(c: ChartData): string {
  switch (c.kind) {
    case "histogram":
      return histogram(c);
    case "box":
      return boxes(c);
    case "bar":
      return bars(c);
    case "tree":
      return tree(c);
    default:
      return xy(c);
  }
}

function svgOpen(w: number, h: number, title: string): string[] {
  return [
    `<svg xmlns='http://www.w3.org/2000/svg' width='${w}' height='${h}' viewBox='0 0 ${w} ${h}' ${FONT} font-size='12'>`,
    `<rect width='${w}' height='${h}' fill='#ffffff'/>`,
    `<text x='16' y='24' font-size='14' font-weight='600' fill='${INK}'>${esc(title)}</text>`,
  ];
}

function legend(parts: string[], items: { name: string; color: string }[], w = W): void {
  if (items.length < 2) return;
  let x = w - M.r;
  const y = 40;
  for (const it of [...items].reverse()) {
    const tw = it.name.length * 6.4 + 22;
    x -= tw;
    parts.push(`<rect x='${x}' y='${y - 8}' width='10' height='10' rx='2' fill='${it.color}'/>`);
    parts.push(`<text x='${x + 14}' y='${y + 1}' fill='${QUIET}' font-size='11'>${esc(it.name)}</text>`);
  }
}

function frame(
  parts: string[],
  xDomain: [number, number] | string[],
  yDomain: [number, number],
  xLabel: string,
  yLabel: string,
  w = W,
  h = H,
): Frame {
  const x0 = M.l, x1 = w - M.r, y0 = M.t + 8, y1 = h - M.b;
  const yt = niceTicks(yDomain[0], yDomain[1]);
  const ylo = Math.min(yDomain[0], yt[0] ?? yDomain[0]);
  const yhi = Math.max(yDomain[1], yt[yt.length - 1] ?? yDomain[1]);
  const sy: Scale = (v) => y1 - ((v - ylo) / (yhi - ylo || 1)) * (y1 - y0);
  for (const t of yt) {
    parts.push(`<line x1='${x0}' x2='${x1}' y1='${sy(t)}' y2='${sy(t)}' stroke='${GRID}'/>`);
    parts.push(`<text x='${x0 - 6}' y='${sy(t) + 4}' text-anchor='end' fill='${QUIET}' font-size='11'>${tick(t)}</text>`);
  }
  let sx: Scale;
  let cats: string[] | null = null;
  if (Array.isArray(xDomain) && typeof xDomain[0] === "string") {
    cats = xDomain as string[];
    const band = (x1 - x0) / Math.max(cats.length, 1);
    sx = (i) => x0 + band * (i + 0.5);
    const every = Math.ceil(cats.length / 14);
    cats.forEach((c, i) => {
      if (i % every) return;
      const label = c.length > 12 ? c.slice(0, 11) + "…" : c;
      parts.push(`<text x='${sx(i)}' y='${y1 + 16}' text-anchor='middle' fill='${QUIET}' font-size='11'>${esc(label)}</text>`);
    });
  } else {
    const [lo0, hi0] = xDomain as [number, number];
    const xt = niceTicks(lo0, hi0);
    const lo = Math.min(lo0, xt[0] ?? lo0), hi = Math.max(hi0, xt[xt.length - 1] ?? hi0);
    sx = (v) => x0 + ((v - lo) / (hi - lo || 1)) * (x1 - x0);
    for (const t of xt) {
      parts.push(`<line x1='${sx(t)}' x2='${sx(t)}' y1='${y0}' y2='${y1}' stroke='${GRID}'/>`);
      parts.push(`<text x='${sx(t)}' y='${y1 + 16}' text-anchor='middle' fill='${QUIET}' font-size='11'>${tick(t)}</text>`);
    }
  }
  parts.push(`<line x1='${x0}' x2='${x1}' y1='${y1}' y2='${y1}' stroke='${AXIS}'/>`);
  parts.push(`<line x1='${x0}' x2='${x0}' y1='${y0}' y2='${y1}' stroke='${AXIS}'/>`);
  if (xLabel) parts.push(`<text x='${(x0 + x1) / 2}' y='${h - 10}' text-anchor='middle' fill='${INK}'>${esc(xLabel)}</text>`);
  if (yLabel)
    parts.push(
      `<text transform='translate(16 ${(y0 + y1) / 2}) rotate(-90)' text-anchor='middle' fill='${INK}'>${esc(yLabel)}</text>`,
    );
  return { parts, sx, sy, cats };
}

function refLines(f: Frame, c: ChartData, w = W, h = H): void {
  const x0 = M.l, x1 = w - M.r, y0 = M.t + 8, y1 = h - M.b;
  for (const r of c.ref_lines ?? []) {
    const isLimit = /UCL|LCL|LSL|USL/.test(r.name);
    const color = isLimit ? ALERT : r.name === "Target" || r.name === "Center" ? "#1a7f37" : QUIET;
    const dash = isLimit ? "6 4" : r.name === "Zero" ? "" : "3 3";
    if (r.axis === "y") {
      const y = f.sy(r.value);
      f.parts.push(`<line x1='${x0}' x2='${x1}' y1='${y}' y2='${y}' stroke='${color}' stroke-width='1.25' stroke-dasharray='${dash}'/>`);
      if (r.name !== "Zero") f.parts.push(`<text x='${x1 + 4}' y='${y + 4}' fill='${color}' font-size='11'>${esc(r.name)} ${refNum(r.value)}</text>`);
    } else {
      const x = f.sx(r.value);
      f.parts.push(`<line x1='${x}' x2='${x}' y1='${y0}' y2='${y1}' stroke='${color}' stroke-width='1.25' stroke-dasharray='${dash}'/>`);
      f.parts.push(`<text x='${x}' y='${y0 - 4}' text-anchor='middle' fill='${color}' font-size='11'>${esc(r.name)}</text>`);
    }
  }
}

function refNum(v: number): string {
  const a = Math.abs(v);
  if (a !== 0 && (a >= 1e6 || a < 1e-3)) return v.toExponential(2);
  return String(Number(v.toPrecision(5)));
}

function num(a: unknown): number[] {
  return Array.isArray(a) ? (a as unknown[]).map((v) => (typeof v === "number" ? v : NaN)) : [];
}

function extent(values: number[]): [number, number] {
  const v = values.filter(Number.isFinite);
  if (!v.length) return [0, 1];
  return [Math.min(...v), Math.max(...v)];
}

function pad([lo, hi]: [number, number], frac = 0.05): [number, number] {
  const d = (hi - lo) * frac || Math.abs(hi) * 0.1 || 1;
  return [lo - d, hi + d];
}

// ------------------------------------------------------------------ XY charts (scatter, line, control, quantile)

function xy(c: ChartData): string {
  const parts = svgOpen(W, H, c.title);
  const series = c.series;
  const categorical = Boolean(c.extra?.["x_categorical"]) || series.some((s) => (s.x ?? []).some((v) => typeof v === "string"));
  let cats: string[] = [];
  if (categorical) {
    const seen = new Set<string>();
    for (const s of series) for (const v of s.x ?? []) if (!seen.has(String(v))) { seen.add(String(v)); cats.push(String(v)); }
  }
  const ys: number[] = [];
  for (const s of series) ys.push(...num(s.y), ...num(s["low"]), ...num(s["high"]));
  for (const r of c.ref_lines ?? []) if (r.axis === "y") ys.push(r.value);
  const xs: number[] = [];
  if (!categorical) {
    for (const s of series) xs.push(...num(s.x));
    for (const r of c.ref_lines ?? []) if (r.axis === "x") xs.push(r.value);
  }
  const f = frame(parts, categorical ? cats : pad(extent(xs), 0.03), pad(extent(ys)), c.x_label, c.y_label);
  const px = (v: number | string, i: number, jitter = false): number => {
    if (!categorical) return f.sx(v as number);
    const k = cats.indexOf(String(v));
    const j = jitter ? (((i * 0.6180339887) % 1) - 0.5) * 0.36 : 0;
    return f.sx(k + j);
  };
  refLines(f, c);
  const legendItems: { name: string; color: string }[] = [];
  series.forEach((s, si) => {
    const color = s.name === "UCL" || s.name === "LCL" ? ALERT : PALETTE[si % PALETTE.length];
    const style = s.style ?? "points";
    const x = s.x ?? [];
    const y = num(s.y);
    const pts = x.map((xv, i) => [px(xv, i, style === "points" && categorical), f.sy(y[i])] as const).filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b));
    if (style !== "error-bar" && !/CI (lower|upper)/.test(s.name) && s.name !== "UCL" && s.name !== "LCL") legendItems.push({ name: s.name, color });
    if (style === "line" || style === "dash" || style === "points-line") {
      parts.push(
        `<polyline fill='none' stroke='${color}' stroke-width='${style === "dash" ? 1 : 1.5}' ${style === "dash" ? "stroke-dasharray='4 3'" : ""} points='${pts.map((p) => p.join(",")).join(" ")}'/>`,
      );
    }
    if (style === "step") {
      const segs: string[] = [];
      for (let i = 0; i < pts.length; i++) {
        const half = i + 1 < pts.length ? (pts[i + 1][0] - pts[i][0]) / 2 : i > 0 ? (pts[i][0] - pts[i - 1][0]) / 2 : 6;
        segs.push(`M${pts[i][0] - half} ${pts[i][1]}H${pts[i][0] + half}`);
      }
      parts.push(`<path d='${segs.join("")}' fill='none' stroke='${color}' stroke-width='1.25' stroke-dasharray='6 4'/>`);
    }
    if (style === "points" || style === "points-line") {
      const flagged = new Set((s["flagged"] as number[] | undefined) ?? []);
      const r = pts.length > 300 ? 2 : 3;
      pts.forEach(([a, b], i) => {
        const bad = flagged.has(i);
        parts.push(`<circle cx='${a}' cy='${b}' r='${bad ? r + 1.5 : r}' fill='${bad ? ALERT : color}' fill-opacity='${style === "points" ? 0.75 : 1}'/>`);
      });
      const labels = s["labels"] as string[] | undefined;
      if (labels) {
        const top = Math.max(0, pts.length - 5);
        pts.forEach(([a, b], i) => {
          if (i >= top) parts.push(`<text x='${a + 6}' y='${b + 4}' fill='${INK}' font-size='11'>${esc(labels[i])}</text>`);
        });
      }
    }
    if (style === "mean-marker") {
      pts.forEach(([a, b]) => parts.push(`<line x1='${a - 18}' x2='${a + 18}' y1='${b}' y2='${b}' stroke='${INK}' stroke-width='2.5'/>`));
    }
    if (style === "error-bar") {
      const lo = num(s["low"]), hi = num(s["high"]);
      x.forEach((xv, i) => {
        const a = px(xv, i);
        const yl = f.sy(lo[i]), yh = f.sy(hi[i]);
        parts.push(`<path d='M${a} ${yl}V${yh}M${a - 6} ${yl}H${a + 6}M${a - 6} ${yh}H${a + 6}' stroke='${INK}' stroke-width='1.25' fill='none'/>`);
      });
    }
  });
  legend(parts, legendItems.filter((l) => l.name !== "Data"));
  const eq = c.extra?.["equation"];
  if (typeof eq === "string") parts.push(`<text x='${M.l + 8}' y='${M.t + 22}' fill='${QUIET}' font-size='11'>${esc(eq)}</text>`);
  parts.push("</svg>");
  return parts.join("");
}

// ------------------------------------------------------------------ histogram

function histogram(c: ChartData): string {
  const parts = svgOpen(W, H, c.title);
  const s = c.series[0];
  const edges = num(s["edges"]);
  const counts = num(s["counts"]);
  const n = counts.reduce((a, b) => a + b, 0);
  const width = edges.length > 1 ? edges[1] - edges[0] : 1;
  const fits: { mean: number; sd: number; name: string; color: string }[] = [];
  const nf = c.extra?.["normal_fit"] as { mean: number; sd: number } | undefined;
  const nw = c.extra?.["normal_fit_within"] as { mean: number; sd: number } | undefined;
  if (nf && nf.sd > 0) fits.push({ ...nf, name: nw ? "Overall" : "Normal fit", color: INK });
  if (nw && nw.sd > 0) fits.push({ ...nw, name: "Within", color: PALETTE[1] });
  const pdf = (x: number, m: number, sd: number) => Math.exp(-0.5 * ((x - m) / sd) ** 2) / (sd * Math.sqrt(2 * Math.PI));
  const xs = [...edges];
  for (const r of c.ref_lines ?? []) if (r.axis === "x") xs.push(r.value);
  let ymax = Math.max(...counts, 1);
  for (const ft of fits) ymax = Math.max(ymax, n * width * pdf(ft.mean, ft.mean, ft.sd));
  const f = frame(parts, pad(extent(xs), 0.02), [0, ymax * 1.08], c.x_label, c.y_label);
  counts.forEach((k, i) => {
    const a = f.sx(edges[i]), b = f.sx(edges[i + 1]);
    parts.push(`<rect x='${a + 0.5}' y='${f.sy(k)}' width='${Math.max(b - a - 1, 0.5)}' height='${f.sy(0) - f.sy(k)}' fill='${PALETTE[0]}' fill-opacity='0.55' stroke='${PALETTE[0]}'/>`);
  });
  const [lo, hi] = pad(extent(xs), 0.02);
  for (const ft of fits) {
    const pts: string[] = [];
    for (let i = 0; i <= 80; i++) {
      const x = lo + ((hi - lo) * i) / 80;
      pts.push(`${f.sx(x)},${f.sy(n * width * pdf(x, ft.mean, ft.sd))}`);
    }
    parts.push(`<polyline fill='none' stroke='${ft.color}' stroke-width='1.5' points='${pts.join(" ")}'/>`);
  }
  refLines(f, c);
  legend(parts, fits.map((ft) => ({ name: ft.name, color: ft.color })));
  parts.push("</svg>");
  return parts.join("");
}

// ------------------------------------------------------------------ box plots

function boxes(c: ChartData): string {
  const parts = svgOpen(W, H, c.title);
  const ss = c.series;
  const vals: number[] = [];
  for (const s of ss) vals.push(...num([s["whisker_low"], s["whisker_high"], s["q1"], s["q3"]]), ...num(s["outliers"]));
  const cats = ss.map((s) => s.name);
  const f = frame(parts, cats, pad(extent(vals)), ss.length > 1 ? c.x_label : "", c.y_label);
  const band = (W - M.l - M.r) / Math.max(cats.length, 1);
  const bw = Math.min(70, band * 0.5);
  ss.forEach((s, i) => {
    const x = f.sx(i);
    const g = (k: string) => f.sy(s[k] as number);
    const color = PALETTE[0];
    parts.push(`<path d='M${x} ${g("whisker_low")}V${g("q1")}M${x} ${g("q3")}V${g("whisker_high")}M${x - bw / 4} ${g("whisker_low")}H${x + bw / 4}M${x - bw / 4} ${g("whisker_high")}H${x + bw / 4}' stroke='${INK}' fill='none'/>`);
    parts.push(`<rect x='${x - bw / 2}' y='${g("q3")}' width='${bw}' height='${g("q1") - g("q3")}' fill='${color}' fill-opacity='0.18' stroke='${color}' stroke-width='1.5'/>`);
    parts.push(`<line x1='${x - bw / 2}' x2='${x + bw / 2}' y1='${g("median")}' y2='${g("median")}' stroke='${INK}' stroke-width='2'/>`);
    parts.push(`<path d='M${x - 4} ${g("mean")}l4 -4l4 4l-4 4z' fill='${INK}'/>`);
    for (const o of num(s["outliers"])) parts.push(`<circle cx='${x}' cy='${f.sy(o)}' r='3' fill='none' stroke='${ALERT}'/>`);
  });
  parts.push("</svg>");
  return parts.join("");
}

// ------------------------------------------------------------------ bar charts

function bars(c: ChartData): string {
  const ss = c.series;
  const cats: string[] = [];
  for (const s of ss) for (const v of s.x ?? []) if (!cats.includes(String(v))) cats.push(String(v));
  const stacked = Boolean(c.extra?.["stacked"]);
  const horizontal = Boolean(c.extra?.["horizontal"]);
  const value = (s: Series, cat: string) => {
    const i = (s.x ?? []).map(String).indexOf(cat);
    return i >= 0 ? num(s.y)[i] : 0;
  };
  let hi = 0;
  for (const cat of cats) {
    const vs = ss.map((s) => value(s, cat));
    hi = Math.max(hi, stacked ? vs.reduce((a, b) => a + b, 0) : Math.max(...vs));
  }
  if (horizontal) return hbars(c, cats, value, hi);
  const parts = svgOpen(W, H, c.title);
  const f = frame(parts, cats, [0, hi * 1.05 || 1], c.x_label, c.y_label);
  const band = (W - M.l - M.r) / Math.max(cats.length, 1);
  const inner = band * 0.7;
  cats.forEach((cat, ci) => {
    let base = 0;
    ss.forEach((s, si) => {
      const v = value(s, cat);
      const color = PALETTE[si % PALETTE.length];
      if (stacked) {
        const y = f.sy(base + v), y2 = f.sy(base);
        parts.push(`<rect x='${f.sx(ci) - inner / 2}' y='${y}' width='${inner}' height='${y2 - y}' fill='${color}' fill-opacity='0.8'/>`);
        base += v;
      } else {
        const w = inner / ss.length;
        const x = f.sx(ci) - inner / 2 + si * w;
        parts.push(`<rect x='${x}' y='${f.sy(v)}' width='${Math.max(w - 2, 1)}' height='${f.sy(0) - f.sy(v)}' fill='${color}' fill-opacity='0.8'/>`);
      }
    });
  });
  legend(parts, ss.map((s, i) => ({ name: s.name, color: PALETTE[i % PALETTE.length] })));
  parts.push("</svg>");
  return parts.join("");
}

function hbars(c: ChartData, cats: string[], value: (s: Series, cat: string) => number, hi: number): string {
  const rowH = 22;
  const h = Math.max(160, M.t + 16 + cats.length * rowH + M.b);
  const left = 150;
  const parts = svgOpen(W, h, c.title);
  const x0 = left, x1 = W - M.r, y0 = M.t + 8;
  const xt = niceTicks(0, hi || 1);
  const top = Math.max(hi, xt[xt.length - 1] ?? hi) || 1;
  const sx = (v: number) => x0 + (v / top) * (x1 - x0);
  for (const t of xt) {
    parts.push(`<line x1='${sx(t)}' x2='${sx(t)}' y1='${y0}' y2='${y0 + cats.length * rowH}' stroke='${GRID}'/>`);
    parts.push(`<text x='${sx(t)}' y='${y0 + cats.length * rowH + 16}' text-anchor='middle' fill='${QUIET}' font-size='11'>${tick(t)}</text>`);
  }
  const s = c.series[0];
  cats.forEach((cat, i) => {
    const y = y0 + i * rowH;
    const v = value(s, cat);
    const label = cat.length > 22 ? cat.slice(0, 21) + "…" : cat;
    parts.push(`<text x='${x0 - 8}' y='${y + rowH / 2 + 4}' text-anchor='end' fill='${INK}' font-size='11'>${esc(label)}</text>`);
    parts.push(`<rect x='${x0}' y='${y + 4}' width='${Math.max(sx(Math.abs(v)) - x0, 0.5)}' height='${rowH - 8}' fill='${PALETTE[0]}' fill-opacity='0.8'/>`);
    parts.push(`<text x='${sx(Math.abs(v)) + 4}' y='${y + rowH / 2 + 4}' fill='${QUIET}' font-size='11'>${esc(fmt(v))}</text>`);
  });
  parts.push(`<line x1='${x0}' x2='${x0}' y1='${y0}' y2='${y0 + cats.length * rowH}' stroke='${AXIS}'/>`);
  if (c.y_label) parts.push(`<text x='${(x0 + x1) / 2}' y='${h - 10}' text-anchor='middle' fill='${INK}'>${esc(c.y_label)}</text>`);
  parts.push("</svg>");
  return parts.join("");
}

// ------------------------------------------------------------------ decision tree

interface TreeNode {
  id: number;
  parent: number | null;
  rule: string;
  n: number;
  prediction: string | number;
  detail: string;
  leaf: boolean;
}

function tree(c: ChartData): string {
  const nodes = (c.series[0]?.["nodes"] as TreeNode[]) ?? [];
  const kids = new Map<number, TreeNode[]>();
  for (const nd of nodes) if (nd.parent !== null) kids.set(nd.parent, [...(kids.get(nd.parent) ?? []), nd]);
  const root = nodes.find((nd) => nd.parent === null);
  if (!root) return svgOpen(W, 80, c.title).concat("</svg>").join("");
  const pos = new Map<number, { x: number; depth: number }>();
  let leafX = 0;
  let maxDepth = 0;
  const place = (nd: TreeNode, depth: number): number => {
    maxDepth = Math.max(maxDepth, depth);
    const ch = kids.get(nd.id) ?? [];
    const x = ch.length ? ch.map((k) => place(k, depth + 1)).reduce((a, b) => a + b, 0) / ch.length : leafX++;
    pos.set(nd.id, { x, depth });
    return x;
  };
  place(root, 0);
  const boxW = 150, gapX = 14, rowH = 92, boxH = 58;
  const w = Math.max(W, leafX * (boxW + gapX) + 32);
  const h = 56 + (maxDepth + 1) * rowH;
  const parts = svgOpen(w, h, c.title);
  const cx = (id: number) => 16 + pos.get(id)!.x * (boxW + gapX) + boxW / 2;
  const cy = (id: number) => 44 + pos.get(id)!.depth * rowH;
  for (const nd of nodes) {
    if (nd.parent === null) continue;
    parts.push(`<path d='M${cx(nd.parent)} ${cy(nd.parent) + boxH}V${cy(nd.id) - 14}H${cx(nd.id)}V${cy(nd.id)}' fill='none' stroke='${AXIS}'/>`);
  }
  for (const nd of nodes) {
    const x = cx(nd.id) - boxW / 2, y = cy(nd.id);
    const pred = typeof nd.prediction === "number" ? fmt(nd.prediction) : nd.prediction;
    const rule = nd.rule.length > 24 ? nd.rule.slice(0, 23) + "…" : nd.rule;
    const detail = nd.detail.length > 26 ? nd.detail.slice(0, 25) + "…" : nd.detail;
    parts.push(`<rect x='${x}' y='${y}' width='${boxW}' height='${boxH}' rx='6' fill='${nd.leaf ? "#eef4ff" : "#ffffff"}' stroke='${nd.leaf ? PALETTE[0] : AXIS}'/>`);
    parts.push(`<text x='${x + 8}' y='${y + 16}' font-weight='600' fill='${INK}' font-size='11'>${esc(rule)}</text>`);
    parts.push(`<text x='${x + 8}' y='${y + 32}' fill='${INK}' font-size='11'>N ${nd.n} · ${esc(String(pred))}</text>`);
    parts.push(`<text x='${x + 8}' y='${y + 48}' fill='${QUIET}' font-size='10.5'>${esc(detail)}</text>`);
  }
  parts.push("</svg>");
  return parts.join("");
}

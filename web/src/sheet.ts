import type { Cell, SheetData } from "./types";

/** Turn a 2-D block of cell values (first row = names) into named columns. */
export function toColumns(values: unknown[][], source: string): SheetData {
  if (!values.length) return { source, columns: {} };
  const header = values[0];
  const body = values.slice(1);
  // Drop trailing rows that are completely empty.
  let end = body.length;
  while (end > 0 && body[end - 1].every((v) => v === "" || v === null || v === undefined)) end--;
  const rows = body.slice(0, end);
  const columns: Record<string, Cell[]> = {};
  const used = new Set<string>();
  header.forEach((h, j) => {
    let name = h === null || h === undefined || String(h).trim() === "" ? `Column ${j + 1}` : String(h).trim();
    const base = name;
    for (let k = 2; used.has(name); k++) name = `${base} (${k})`;
    used.add(name);
    const col = rows.map((r) => normalise(r[j]));
    if (col.every((v) => v === null) && base === `Column ${j + 1}`) return; // empty, unnamed
    columns[name] = col;
  });
  return { source, columns };
}

function normalise(v: unknown): Cell {
  if (v === undefined || v === null) return null;
  if (typeof v === "string") return v.trim() === "" ? null : v;
  if (typeof v === "number" || typeof v === "boolean") return v;
  return String(v);
}

/** Rows to write for one result: a title, notes, then each table with a caption and header. */
export function resultBlocks(result: { title: string; notes: string[]; tables: { title: string; columns: string[]; rows: Cell[][] }[] }) {
  const blocks: { kind: "title" | "note" | "caption" | "header" | "body"; values: Cell[][] }[] = [];
  blocks.push({ kind: "title", values: [[result.title]] });
  for (const n of result.notes) blocks.push({ kind: "note", values: [[n]] });
  for (const t of result.tables) {
    blocks.push({ kind: "caption", values: [[t.title]] });
    blocks.push({ kind: "header", values: [t.columns] });
    if (t.rows.length) blocks.push({ kind: "body", values: t.rows.map((r) => r.map((v) => (v === null ? "" : v))) });
  }
  return blocks;
}

/** Spreadsheet number format for one value, so exported cells read like the panel. */
export function numberFormat(v: unknown): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "General";
  if (Number.isInteger(v) && Math.abs(v) < 1e15) return "0";
  const a = Math.abs(v);
  if (a !== 0 && (a < 1e-4 || a >= 1e9)) return "0.000E+00";
  return "0.0####";
}

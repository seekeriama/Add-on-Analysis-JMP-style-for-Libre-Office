// Host for Excel (web, Windows, Mac): Office.js for the workbook, Pyodide in a
// Web Worker for the Python core.

/// <reference types="office-js" />
import { numberFormat, resultBlocks, toColumns } from "../sheet";
import type { AnalysisRequest, AnalysisResponse, Host, ResultData, SheetData } from "../types";

export class ExcelHost implements Host {
  readonly name = "Excel";
  private worker: Worker;
  private nextId = 1;
  private pending = new Map<number, (r: AnalysisResponse) => void>();
  private statusCb: (m: string) => void = () => {};

  constructor(workerUrl = "pyodide-worker.js") {
    const pyodide = new URLSearchParams(location.search).get("pyodide");
    this.worker = new Worker(pyodide ? `${workerUrl}?pyodide=${encodeURIComponent(pyodide)}` : workerUrl);
    this.worker.onmessage = (e: MessageEvent) => {
      const msg = e.data as { id?: number; status?: string; response?: AnalysisResponse };
      if (msg.status) this.statusCb(msg.status);
      if (msg.id !== undefined && msg.response) {
        this.pending.get(msg.id)?.(msg.response);
        this.pending.delete(msg.id);
      }
    };
    this.worker.postMessage({ type: "init" });
  }

  onStatus(cb: (m: string) => void): void {
    this.statusCb = cb;
  }

  readSelection(): Promise<SheetData> {
    return Excel.run(async (ctx) => {
      let range = ctx.workbook.getSelectedRange();
      range.load(["cellCount", "address"]);
      await ctx.sync();
      if (range.cellCount === 1) {
        // A single cell: use the block of data around it.
        range = range.getSurroundingRegion();
      }
      range.load(["values", "address"]);
      await ctx.sync();
      return toColumns(range.values as unknown[][], range.address);
    });
  }

  run(request: AnalysisRequest): Promise<AnalysisResponse> {
    const id = this.nextId++;
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      this.worker.postMessage({ type: "run", id, request });
    });
  }

  exportResult(result: ResultData, chartSvgs: string[]): Promise<string> {
    return Excel.run(async (ctx) => {
      const sheets = ctx.workbook.worksheets;
      sheets.load("items/name");
      await ctx.sync();
      const names = new Set(sheets.items.map((s) => s.name));
      let name = "CellStat 1";
      for (let i = 2; names.has(name); i++) name = `CellStat ${i}`;
      const ws = sheets.add(name);

      let row = 0;
      for (const b of resultBlocks(result)) {
        const width = Math.max(...b.values.map((r) => r.length));
        const values = b.values.map((r) => [...r, ...Array(width - r.length).fill("")]);
        const rg = ws.getRangeByIndexes(row, 0, values.length, width);
        rg.values = values as (string | number | boolean)[][];
        if (b.kind === "body") rg.numberFormat = values.map((r) => r.map(numberFormat));
        if (b.kind === "title") rg.format.font.set({ bold: true, size: 14 });
        if (b.kind === "caption") rg.format.font.bold = true;
        if (b.kind === "header") {
          rg.format.font.bold = true;
          rg.format.fill.color = "#EEF1F5";
        }
        if (b.kind === "note") rg.format.font.italic = true;
        row += values.length + (b.kind === "body" ? 1 : 0);
      }
      const used = ws.getUsedRange();
      used.format.autofitColumns();
      used.load("width");
      await ctx.sync();

      let top = 10;
      for (const svg of chartSvgs) {
        // Excel's addImage takes PNG or JPEG, so rasterise the SVG at 2x for sharpness.
        const shape = ws.shapes.addImage(await svgToPngBase64(svg, 2));
        const w = Number(/width='(\d+)'/.exec(svg)?.[1] ?? 560);
        shape.width = w * 0.75; // CSS px to points
        shape.left = used.width + 24;
        shape.top = top;
        shape.load("height");
        await ctx.sync();
        top += shape.height + 16;
      }
      ws.activate();
      await ctx.sync();
      return name;
    });
  }
}

/** Rasterise a standalone SVG string to a base64 PNG (no data: prefix). */
export async function svgToPngBase64(svg: string, scale = 2): Promise<string> {
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  try {
    const img = new Image();
    await new Promise<void>((ok, fail) => {
      img.onload = () => ok();
      img.onerror = () => fail(new Error("Could not draw the chart"));
      img.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    const g = canvas.getContext("2d")!;
    g.scale(scale, scale);
    g.drawImage(img, 0, 0);
    return canvas.toDataURL("image/png").split(",")[1];
  } finally {
    URL.revokeObjectURL(url);
  }
}

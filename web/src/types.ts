// Shapes shared with the Python core (see core/cellstat/result.py and api.py).

export type Cell = string | number | boolean | null;

export interface TableData {
  title: string;
  columns: string[];
  rows: Cell[][];
}

export interface Series {
  name: string;
  style?: string;
  x?: (number | string)[];
  y?: number[];
  [key: string]: unknown;
}

export interface RefLine {
  axis: "x" | "y";
  value: number;
  name: string;
}

export interface ChartData {
  kind: "histogram" | "box" | "scatter" | "line" | "bar" | "control" | "quantile" | "tree";
  title: string;
  x_label: string;
  y_label: string;
  series: Series[];
  ref_lines: RefLine[];
  extra?: Record<string, unknown>;
}

export interface ResultData {
  analysis: string;
  title: string;
  tables: TableData[];
  charts: ChartData[];
  notes: string[];
}

export interface AnalysisRequest {
  analysis: string;
  columns: Record<string, Cell[]>;
  roles: Record<string, string[]>;
  options: Record<string, unknown>;
}

export type AnalysisResponse =
  | { ok: true; results: ResultData[] }
  | { ok: false; error: string; trace?: string };

/** A data table read from the spreadsheet: first row of the range = column names. */
export interface SheetData {
  source: string;
  columns: Record<string, Cell[]>;
}

/** What the panel needs from the spreadsheet app it runs in. */
export interface Host {
  readonly name: string;
  /** Read the selected range (or the region around the cursor). */
  readSelection(): Promise<SheetData>;
  /** Run an analysis in the Python core. */
  run(request: AnalysisRequest): Promise<AnalysisResponse>;
  /** Write a result to a new sheet: tables as cells, charts as SVG pictures. */
  exportResult(result: ResultData, chartSvgs: string[]): Promise<string>;
  /** Optional status line while the engine loads. */
  onStatus?(cb: (msg: string) => void): void;
}

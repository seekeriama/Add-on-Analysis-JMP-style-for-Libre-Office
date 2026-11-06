// Host for the LibreOffice extension: the panel is served by a small local
// server inside LibreOffice, which reads and writes the spreadsheet over UNO.

import type { AnalysisRequest, AnalysisResponse, Host, ResultData, SheetData } from "../types";

export class HttpHost implements Host {
  readonly name = "LibreOffice Calc";
  private token = new URLSearchParams(location.search).get("token") ?? "";

  private async call<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json", "X-CellStat-Token": this.token },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
    if (!res.ok) throw new Error((data as { error?: string }).error ?? `HTTP ${res.status}`);
    return data as T;
  }

  readSelection(): Promise<SheetData> {
    return this.call<SheetData>("/api/selection");
  }

  run(request: AnalysisRequest): Promise<AnalysisResponse> {
    return this.call<AnalysisResponse>("/api/run", request);
  }

  async exportResult(result: ResultData, chartSvgs: string[]): Promise<string> {
    const r = await this.call<{ sheet: string }>("/api/export", { result, charts: chartSvgs });
    return r.sheet;
  }

  onStatus(cb: (msg: string) => void): void {
    cb("Connected to LibreOffice Calc");
  }
}

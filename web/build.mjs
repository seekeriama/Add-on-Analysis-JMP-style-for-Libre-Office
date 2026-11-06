// Builds the panel for both hosts:
//   dist/excel/        Excel task pane (served over HTTPS, see excel-addin/)
//   dist/libreoffice/  panel served by the LibreOffice extension
import { build } from "esbuild";
import { cpSync, mkdirSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";

rmSync("dist", { recursive: true, force: true });
const common = { bundle: true, minify: true, sourcemap: false, target: "es2020", logLevel: "info" };

await build({ ...common, entryPoints: ["src/main-excel.ts"], outfile: "dist/excel/taskpane.js", format: "iife" });
await build({ ...common, entryPoints: ["src/pyodide-worker.ts"], outfile: "dist/excel/pyodide-worker.js", format: "iife" });
await build({ ...common, entryPoints: ["src/main-lo.ts"], outfile: "dist/libreoffice/panel.js", format: "iife" });

for (const target of ["excel", "libreoffice"]) {
  mkdirSync(`dist/${target}`, { recursive: true });
  cpSync("public/style.css", `dist/${target}/style.css`);
  cpSync("public/icon-32.png", `dist/${target}/icon-32.png`);
  cpSync("public/icon-80.png", `dist/${target}/icon-80.png`);
  cpSync("public/icon-16.png", `dist/${target}/icon-16.png`);
}
cpSync("public/taskpane.html", "dist/excel/taskpane.html");
cpSync("public/panel.html", "dist/libreoffice/index.html");

// The Python core travels with the Excel task pane as a zip that Pyodide unpacks.
execFileSync("zip", ["-qr", "../web/dist/excel/cellstat-core.zip", "cellstat", "-x", "*__pycache__*"], { cwd: "../core" });
console.log("Built dist/excel and dist/libreoffice");

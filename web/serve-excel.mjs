// HTTPS dev server for the Excel task pane at https://localhost:3000.
// Uses the trusted localhost certificate from `npx office-addin-dev-certs install`.
import { createServer } from "node:https";
import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { extname, join, normalize } from "node:path";

const certDir = join(homedir(), ".office-addin-dev-certs");
const keyFile = join(certDir, "localhost.key");
if (!existsSync(keyFile)) {
  console.error("No dev certificate. Run: npx office-addin-dev-certs install");
  process.exit(1);
}
const root = new URL("./dist/excel/", import.meta.url).pathname;
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".zip": "application/zip" };
createServer({ key: readFileSync(keyFile), cert: readFileSync(join(certDir, "localhost.crt")) }, (req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "https://localhost").pathname)).replace(/^(\.\.[/\\])+/, "");
  const file = join(root, path === "/" ? "taskpane.html" : path);
  if (!file.startsWith(root) || !existsSync(file)) {
    res.writeHead(404).end("not found");
    return;
  }
  res.writeHead(200, { "Content-Type": types[extname(file)] ?? "application/octet-stream", "Access-Control-Allow-Origin": "*" });
  res.end(readFileSync(file));
}).listen(3000, () => console.log("Serving dist/excel at https://localhost:3000"));

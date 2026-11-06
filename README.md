# CellStat

Statistical analysis for **LibreOffice Calc** and **Excel**, in the spirit of desktop
statistics packages: select your data, explore results in an interactive panel, then
export tables and charts to a new sheet. MIT licensed.

Both apps share one Python statistics engine and one web panel, so results are identical
in each.

| Analysis | What you get |
| --- | --- |
| Distribution | Histogram with normal fit, box plot, normal quantile plot, quantiles, summary statistics, Shapiro-Wilk and Anderson-Darling |
| Fit Y by X | Picks by column type: line fit with confidence band (numeric × numeric), one-way ANOVA with Tukey HSD, Levene, Bartlett and Welch (numeric × categorical), contingency table with chi-square and Fisher's exact (categorical × categorical) |
| Multiple regression | Least squares with numeric and categorical terms, effect tests, VIF, residual plots |
| Decision tree | Classification or regression tree, leaf rules, column contributions, optional validation hold-out |
| Control charts | I-MR, X̄-R, X̄-S, p and c charts with Western Electric rules 1 to 4 |
| Process capability | Cp, Cpk, Pp, Ppk, Cpm with confidence intervals, expected and observed PPM |
| Gauge R&R | Crossed study by the ANOVA method, variance components, % study variation, % tolerance, number of distinct categories |
| Design of experiments | Two-level full and fractional factorial designs (up to 7 factors), then effects, Pareto and half-normal plots |

## How it fits together

```
core/          Python package `cellstat`: every analysis, JSON in → tables + chart specs out
web/           The panel (TypeScript, no framework) and its SVG charts, built for both hosts
  src/hosts/excel.ts   Office.js + Pyodide (the Python core running in the browser)
  src/hosts/http.ts    talks to the LibreOffice extension's local server
libreoffice/   .oxt extension: menu entry, local panel server, UNO read/write
excel-addin/   Office add-in manifest
```

Excel on Linux runs as Excel for the web, so the Excel side is an Office.js task pane.
LibreOffice has no embedded browser for extensions, so the extension serves the same panel
on `127.0.0.1` (random port, random per-session token) and opens it in your default browser.
No data leaves your computer in either app.

## LibreOffice Calc

Requirements: LibreOffice 7 or later with Python, plus NumPy and SciPy for LibreOffice's
Python (scikit-learn for decision trees). On Debian or Ubuntu:

```sh
sudo apt install libreoffice-script-provider-python python3-numpy python3-scipy python3-sklearn
```

Build and install:

```sh
cd web && npm install && npm run build && cd ..
libreoffice/build.sh                       # → libreoffice/dist/cellstat.oxt
unopkg add libreoffice/dist/cellstat.oxt   # or Tools > Extension Manager > Add
```

Restart LibreOffice, open a spreadsheet, select a table whose first row holds column
names, and choose **CellStat > Open analysis panel**.

## Excel (web, Windows, Mac)

The task pane is hosted on GitHub Pages from `main` by `.github/workflows/pages.yml`
(one-time setup: **Settings > Pages > Source: GitHub Actions**).

In Excel for the web: **Home > Add-ins > More add-ins > My add-ins > Upload my add-in**, and
choose `excel-addin/manifest.xml`. The **Analyze** button appears on the **Data** tab.

The first run downloads Pyodide with NumPy and SciPy (about 20 MB from cdn.jsdelivr.net);
the browser caches it afterwards. To self-host Pyodide, open the task pane with
`?pyodide=<your copy>/`.

For local development, serve the pane yourself and upload `excel-addin/manifest.dev.xml`:

```sh
cd web && npm install && npm run build
npm run certs            # once: trusted HTTPS certificate for localhost
npm run serve:excel      # serves dist/excel at https://localhost:3000
```

## Tests

```sh
cd core && python3 -m pytest          # 29 tests; reference values from NIST StRD Longley and R
cd web && npm test                    # sheet and number formatting
```

CI runs both on every pull request and builds `cellstat.oxt` as a downloadable artifact.

End-to-end checks that drive a headless LibreOffice and a browser live in
`libreoffice/tests/` and `web/test/excel/`.

## Accuracy

Regression is checked against the NIST StRD Longley certified values (coefficients and
standard errors to 8 significant digits). One-way ANOVA, Tukey HSD, Bartlett and Welch
match R's `aov`, `TukeyHSD`, `bartlett.test` and `oneway.test` on the PlantGrowth data.
Control chart constants d2 and d3 are computed by numerical integration and match the
published tables.

## License

MIT. See [LICENSE](LICENSE). Dependencies: NumPy, SciPy, scikit-learn (BSD-3), Pyodide
(MPL-2.0, loaded unmodified at run time).

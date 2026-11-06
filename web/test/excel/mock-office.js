// Minimal stand-in for Office.js so the Excel task pane can run in a plain browser.
// Records every write in window.__excel for the test to inspect.
(function () {
  const data = window.__sheetData; // 2-D array, first row = names
  const log = { sheets: ["Sheet1"], writes: [], images: [], formats: [] };
  window.__excel = log;
  const queue = [];
  function range(values, address) {
    return {
      values, address, cellCount: values.length * (values[0] || []).length,
      load() { return this; },
      getSurroundingRegion() { return range(data, "Sheet1!A1:" + String.fromCharCode(64 + data[0].length) + data.length); },
      format: { font: { set() {}, bold: false, italic: false }, fill: {}, autofitColumns() {} },
    };
  }
  function sheet(name) {
    return {
      name,
      getRangeByIndexes(r, c, h, w) {
        const rg = range([], `${name}!R${r + 1}C${c + 1}`);
        Object.defineProperty(rg, "values", { set(v) { log.writes.push({ sheet: name, row: r, values: v }); }, get() { return []; } });
        Object.defineProperty(rg, "numberFormat", { set(v) { log.formats.push(v); }, get() { return []; } });
        return rg;
      },
      getUsedRange() { return { format: { autofitColumns() {} }, load() {}, width: 400 }; },
      shapes: { addImage(b64) { log.images.push(b64.length); return { load() {}, height: 255 }; } },
      activate() { log.active = name; },
    };
  }
  window.Office = { onReady(cb) { setTimeout(cb, 0); return Promise.resolve(); } };
  window.Excel = {
    run(cb) {
      const ctx = {
        workbook: {
          getSelectedRange() { return range([["x"]], "Sheet1!A1"); },
          worksheets: {
            items: log.sheets.map((n) => ({ name: n })),
            load() {},
            add(n) { log.sheets.push(n); return sheet(n); },
          },
        },
        sync: async () => {},
      };
      return cb(ctx);
    },
  };
})();

import { test } from "node:test";
import assert from "node:assert/strict";
import { numberFormat, toColumns } from "../src/sheet.ts";
import { fmt, niceTicks } from "../src/format.ts";

test("first row becomes column names, blanks become null, empty trailing rows dropped", () => {
  const d = toColumns([["weight", "group", ""], [1.5, "a", ""], ["", "b", ""], ["", "", ""]], "A1:C4");
  assert.deepEqual(Object.keys(d.columns), ["weight", "group"]);
  assert.deepEqual(d.columns.weight, [1.5, null]);
  assert.deepEqual(d.columns.group, ["a", "b"]);
});

test("duplicate and missing names are made unique", () => {
  const d = toColumns([["x", "x", ""], [1, 2, 3]], "s");
  assert.deepEqual(Object.keys(d.columns), ["x", "x (2)", "Column 3"]);
});

test("number formats", () => {
  assert.equal(numberFormat(3), "0");
  assert.equal(numberFormat(0.0159), "0.0####");
  assert.equal(numberFormat(1.2e-7), "0.000E+00");
  assert.equal(numberFormat("text"), "General");
});

test("display formatting", () => {
  assert.equal(fmt(0.00001, "p-value"), "<.0001");
  assert.equal(fmt(4.846087862), "4.84609");
  assert.equal(fmt(null), "");
  assert.deepEqual(niceTicks(0, 10, 5), [0, 2, 4, 6, 8, 10]);
});

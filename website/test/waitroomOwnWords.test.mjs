// A waiting note the Assistant passed on is shown in the owner's own words (the owner, 2026-11-04): the row keeps the Assistant's version
// beside them (waitroom.SEP, "\x1f"), and the queue drew the two run together.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const src = fs.readFileSync(new URL("../src/ui.jsx", import.meta.url), "utf8");

test("the queue shows the owner's words, never the Assistant's version kept beside them", () => {
  const m = src.match(/export const ownWords = (\(note\) => [^;]+);/);
  assert.ok(m, "ownWords is defined");
  const ownWords = eval(m[1]);
  assert.equal(ownWords("Also put Northwind Payroll on the list, please.\x1fAlso add Northwind Payroll to vendors-2026.txt."), "Also put Northwind Payroll on the list, please.");
  assert.equal(ownWords("use the main branch"), "use the main branch");
  assert.match(src, /title=\{ownWords\(w\.Note\)\}/);
  assert.match(src, />\{ownWords\(w\.Note\)\}<\/Typography>/);
});

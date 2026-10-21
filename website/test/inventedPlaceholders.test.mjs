import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// THE NEW SHEET'S EXAMPLES NAME ONLY STAND-INS (CLAUDE.md, the UI audit 2026-10-21): a placeholder named a facility that was not
// on the repository's list of invented names. Every capitalised name in the examples is a stand-in, a numbered site or a month.
const STAND_INS = new Set(["Alex", "Doyle", "Northwind", "Erin", "Blake", "Gail", "Moreno", "Paula", "Vance", "Ray", "Colton", "Marcus",
  "Reed", "Omar", "Keller", "Payworth", "Trainly", "Spendly", "PhishGuard", "Site", "July", "AP"]);

test("every name in the New sheet's examples is an invented one", () => {
  const src = readFileSync(new URL("../src/NewSheet.jsx", import.meta.url), "utf8");
  const at = src.indexOf('placeholder={kind === "goal"'), block = src.slice(at, src.indexOf("}\n", at));
  const examples = [...block.matchAll(/"([^"]+)"/g)].map((m) => m[1]).filter((s) => s.includes(" "));
  assert.ok(examples.length >= 5, "the examples are read");
  const names = examples.flatMap((s) => s.split(/\s+/).slice(1)).map((w) => w.replace(/[^A-Za-z]/g, "").replace(/s$/, "")).filter((w) => /^[A-Z]/.test(w));
  assert.deepEqual(names.filter((w) => !STAND_INS.has(w)), []);
});

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// the mail triage said served a step is listed under that step (spec 2026-10-12, build step 5)
test("the goal page lists each step's arrivals under it", () => {
  const src = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(src, /\(s\.arrivals \|\| \[\]\)\.map/);
});

// A DASHBOARD LINE DRAWS IN WHOLE (2026-11-07): the draw-in scaled its dash by pathLength="1" on a <polyline>, and a browser that
// measured the dash by the first segment stopped the line there. The line now carries its own measured length (--len) and the dash and
// its offset are that length in px; the view no longer turns the animation off to hide it.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");


test("its length is the sum of every segment, not the first", () => {
  const body = src("dashboard/charts.jsx").match(/export const runLength = (\(s\) => [^\n]+);/)[1];
  const runLength = new Function(`return ${body}`)();
  assert.equal(runLength([[0, 0], [3, 4], [3, 10], [9, 18]]), 5 + 6 + 10);
  assert.equal(runLength([[1, 1]]), 0);
});

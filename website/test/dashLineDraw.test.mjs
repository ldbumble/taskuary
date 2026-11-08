// A DASHBOARD LINE DRAWS IN WHOLE (2026-11-07): the draw-in scaled its dash by pathLength="1" on a <polyline>, and a browser that
// measured the dash by the first segment stopped the line there. The line now carries its own measured length (--len) and the dash and
// its offset are that length in px; the view no longer turns the animation off to hide it.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the line is dashed by its own measured length, never by pathLength", () => {
  const charts = src("dashboard/charts.jsx"), css = src("dashboard/dashboard.css");
  assert.doesNotMatch(charts, /<polyline[^>]*pathLength/);
  assert.match(charts, /className="ln" style=\{\{ "--len": Math\.ceil\(runLength\(s\)\) \+ 1 \}\}/);
  assert.match(css, /\.tq-dash-svg \.ln \{ stroke-dasharray: calc\(var\(--len, 0\) \* 1px\); animation: tq-dash-draw/);
  assert.match(css, /@keyframes tq-dash-draw \{ from \{ stroke-dashoffset: calc\(var\(--len, 0\) \* 1px\); \}/);
  assert.doesNotMatch(src("viewSpec.css"), /\.tq-dash-svg \.ln \{[^}]*animation: none/);
});

test("its length is the sum of every segment, not the first", () => {
  const body = src("dashboard/charts.jsx").match(/export const runLength = (\(s\) => [^\n]+);/)[1];
  const runLength = new Function(`return ${body}`)();
  assert.equal(runLength([[0, 0], [3, 4], [3, 10], [9, 18]]), 5 + 6 + 10);
  assert.equal(runLength([[1, 1]]), 0);
});

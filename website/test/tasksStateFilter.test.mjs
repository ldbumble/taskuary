// On the Tasks page a row's state chip is the filter inside In progress (the owner, 2026-09-28: "filter by waiting to
// start / on you / agent waiting on you ... as minimal as possible" - "on the tasks page, not where else").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("clicking a row's state chip narrows In progress to that state, and its pill clears it", () => {
  const s = src("TasksView.jsx");
  assert.match(s, /const \[only, setOnly\] = useState\(null\);/);
  assert.match(s, /\(!only \|\| filter !== "live" \|\| stateOf\(x\)\.label === only\)/);
  assert.match(s, /setFilter\("live"\); setOnly\(only \? null : st\.label\);/);
  assert.match(s, /label=\{`\$\{only\} ✕`\} onClick=\{\(\) => setOnly\(null\)\}/);
});

test("the rail has no state filter - it lives on the Tasks page only", () => {
  assert.ok(!src("AssistantView.jsx").includes("setOnly"));
});

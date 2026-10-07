import { taskSource } from "./taskSource.mjs";
// On the Tasks page a row's state chip is the filter inside In progress (the owner, 2026-09-28: "filter by waiting to
// start / on you / agent waiting on you ... as minimal as possible" - "on the tasks page, not where else").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("clicking a row's state chip narrows In progress to that state, and its pill clears it", () => {
  const s = taskSource();
  assert.match(s, /const \[only, setOnly\] = useState\(null\);/);
  assert.match(s, /\(!only \|\| filter !== "live" \|\| stateOf\(x\)\.label === only\)/);
  assert.match(s, /setFilter\("live"\); setOnly\(only \? null : st\.label\);/);
});

test("the states are pills on top of In progress, with counts and an 'all' that clears", () => {
  const s = taskSource();
  assert.match(s, /filter === "live" && !search && \(liveStates\.length > 1 \|\| only\) &&/);   // a set filter keeps its way out
  assert.match(s, /if \(only && tasks && !liveStates\.some\(\(x\) => x\.key === only\)\) setOnly\(null\)/);   // a state that emptied lets go
  assert.match(s, /<FilterPills value=\{only \|\| ""\} onChange=\{\(k\) => setOnly\(k \|\| null\)\}/);
  assert.match(s, /\{ key: "", label: "all", n: liveStates\.reduce/);
});

test("the rail has no state filter - it lives on the Tasks page only", () => {
  assert.ok(!src("AssistantView.jsx").includes("setOnly"));
});

test("a ranked row wears its place in the batch, circled", () => {
  const s = src("AssistantView.jsx");
  assert.match(s, /const CIRCLED = "①②③④/);
  assert.match(s, /const rankNo = pile\?\.rank_numbers \|\| \{\};/);
  assert.match(s, /\{!!rankNo\[i\.key\] && <span className="tq-pile-rank"/);
});

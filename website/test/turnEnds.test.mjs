import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// A TURN THAT ENDED HAS NOTHING STILL AT WORK (the owner, 2026-11-05: a step kept its spinner under the answer)
test("an ended turn draws a step that never got its result as done, never spinning", () => {
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /const calm = \(st\) => \(!now && st\.status === "running" \? \{ \.\.\.st, status: "done", alongside: false \}/);
  // ...and in a chat a turn with no summary says no "failed" either
  assert.match(ws, /: chat && \(st\.status === "error" \|\| st\.status === "recovered"\) \? \{ \.\.\.st, status: "done" \} : st\);/);
});


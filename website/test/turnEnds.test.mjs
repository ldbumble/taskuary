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


// A TURN AT WORK ALWAYS DRAWS ITS HEAD (2026-11-17: a turn that carried on after the agent's first message folded into the turn above - no
// clock, no Stop x - and the head over it read the first turn's "ran 27s" as if nothing were at work): only a finished turn after a turn folds
test("a working turn after a finished turn keeps its own head, with the clock and the Stop x", () => {
  const ws = read("GeneralWorkspace.jsx");
  const fold = new Function("prev", "x", `return ${ws.match(/<ConvTurn key=\{x\.id\} t=\{x\} more=\{(.*?)\} name=/)[1]};`);
  const done = { kind: "turn", id: "t:a:17:0", state: "done" };
  for (const state of ["working", "starting"]) assert.equal(fold(done, { kind: "turn", id: "t:a:17:1", state }), false, `a ${state} turn draws its head`);
  assert.equal(fold(done, { kind: "turn", id: "t:a:17:1", state: "done" }), true, "a finished turn after a turn still folds into it");
  // ...and the head a live turn draws is the one RunClock, which carries the Stop x (StopCtx)
  assert.match(ws, /\{!more && <div className="tq-aui-role">\{name\}\{live \? <RunClock start=/);
});

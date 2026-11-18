import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// "STARTING …" IS THE WORKING LINE'S QUIET LINE (the owner, 2026-11-05: no boxes), and its clock counts from no earlier than the line came up -
// a turn carried on by new mail counted from the input before it ("62m 16s" at its start)
// ...and since 2026-11-10 no line of words at all ("don't want the working... thing ... it should show agent and time and how long it's running
// rightg away. under it it can spin like normal"): a start is the spin under the turn's head, its clock the head's, from the press
test("a start is the spin under the turn's head, never a line of words", () => {
  // ...ONE PLACE DRAWS A STARTING TURN, the chat's own (ConvTurn - the owner, 2026-11-16): no band of its own before the chat is read
  const ws = read("GeneralWorkspace.jsx"), turn = ws.slice(ws.indexOf("const ConvTurn"), ws.indexOf("const RetryCtx"));
  assert.match(turn, /\{\.\.\.\(t\.state === "starting" \? \{ "data-tq-starting-line": "" \} : \{\}\)\}/);
  assert.match(turn, /<RunClock start=/);
  assert.doesNotMatch(ws, /const AgentBand|<AgentBand/);
  assert.match(read("RunClock.jsx"), /export const RunClock = \(\{ start/);
});

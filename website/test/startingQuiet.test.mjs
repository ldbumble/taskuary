import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// "STARTING …" IS THE WORKING LINE'S QUIET LINE (the owner, 2026-11-05: no boxes), and its clock counts from no earlier than the line came up -
// a turn carried on by new mail counted from the input before it ("62m 16s" at its start)
// ...and since 2026-11-10 no line of words at all ("don't want the working... thing ... it should show agent and time and how long it's running
// rightg away. under it it can spin like normal"): a start is the spin under the turn's head, its clock the head's, from the press
test("a start is the spin under the turn's head, never a line of words", () => {
  const ws = read("GeneralWorkspace.jsx"), band = ws.slice(ws.indexOf("const AgentBand"), ws.indexOf("// The speaker of the agent's turns"));
  assert.match(band, /"data-tq-starting-line": ""/);
  assert.doesNotMatch(band, /className="tq-aui-band"|<span>\{starting\}<\/span>/);
  assert.match(band, /const RunClock = \(\{ start \}\)/);
});

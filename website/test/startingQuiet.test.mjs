import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// "STARTING …" IS THE WORKING LINE'S QUIET LINE (the owner, 2026-11-05: no boxes), and its clock counts from no earlier than the line came up -
// a turn carried on by new mail counted from the input before it ("62m 16s" at its start)
test("the starting line is a quiet line with an honest clock", () => {
  const ws = read("GeneralWorkspace.jsx"), band = ws.slice(ws.indexOf("const AgentBand"), ws.indexOf("// The speaker of the agent's turns"));
  assert.match(band, /<div className="tq-aui-working" role="status" aria-live="polite" data-tq-starting-line="">/);
  assert.doesNotMatch(band, /className="tq-aui-band"/);
  assert.match(band, /elapsedText\(now - Math\.max\(since \|\| 0, shown\)\)/);
});

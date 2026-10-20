// The 2026-10-19 UI walk: "Walk me through my tasks" swallowed presses for a second or two after load - the button greyed on one list
// of conditions and start() returned on another, so a press could look taken and do nothing. One value answers both.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("the Walk button and start() read the same walkOff", () => {
  assert.match(src, /const walkOff = busy \|\| resetting \|\| !!handoff \|\| starting;/);
  assert.match(src, /const start = async \(what\) => \{\s*if \(walkOff \|\| turnFlight\.current \|\| startFlight\.current\) return;/);
  assert.match(src, /className="tq-chip primary" disabled=\{walkOff \|\| walkQueued \|\| \(!pileLoading && !canAdvance\)\}/);
});

test("a press kept while the rows load waits for walkOff to clear, rather than being refused by start()", () => {
  assert.match(src, /if \(!walkQueued \|\| pileLoading \|\| walkOff\) return;/);
  assert.match(src, /\}, \[walkQueued, pileLoading, canAdvance, walkOff\]\);/);
});

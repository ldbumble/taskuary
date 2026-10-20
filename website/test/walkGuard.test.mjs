// The 2026-10-19 UI walk: "Walk me through my tasks" swallowed presses for a second or two after load - the button greyed on one list
// of conditions and start() returned on another, so a press could look taken and do nothing. One value answers both.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("the Walk button and start() read the same walkOff - and a press while it is set is held, not dropped", () => {
  assert.match(src, /const walkOff = busy \|\| resetting \|\| !!handoff \|\| starting;/);
  // A WALK PRESSED WHILE THE WALK IS BUSY IS HELD (owner-approved, 2026-10-20): start() keeps it instead of returning on it
  assert.match(src, /const start = async \(what\) => \{[^]{0,400}if \(walkOff \|\| turnFlight\.current \|\| startFlight\.current\) \{ if \(!starting && !startFlight\.current\) setWalkQueued\(true\); return; \}/);
  // ...so the button greys only for what will not clear by itself: a press held, a walk starting, a reset, a phone hand-off
  assert.match(src, /className="tq-chip primary" disabled=\{walkQueued \|\| starting \|\| resetting \|\| !!handoff \|\| \(!counting && !canAdvance && !onYou\)\}/);
  assert.match(src, /onClick=\{\(\) => \(counting \|\| walkOff \? setWalkQueued\(true\) : start\(null\)\)\}/);
});

test("a held press waits for walkOff to clear and the day to be counted, rather than being refused by start()", () => {
  assert.match(src, /if \(!walkQueued \|\| walkOff \|\| turnFlight\.current \|\| \(counting && !canAdvance\) \|\| pileLoading\) return;\s*setWalkQueued\(false\);\s*if \(canAdvance \|\| onYou\) start\(null\);/);
  assert.match(src, /\}, \[walkQueued, pileLoading, counting, canAdvance, onYou, walkOff\]\);/);
});

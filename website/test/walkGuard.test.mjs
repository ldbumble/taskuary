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

// The owner, 2026-10-23: "I hit walk me through my tasks and it just hung there and we don't need the words. it should just be ..."
test("a Walk press posts no line of the owner's - only the \"…\", from the press until the first item lands", () => {
  const start = src.match(/const start = async \(what\) => \{[^]*?\n  \};/)[0];
  assert.doesNotMatch(start, /role: "user"/);
  assert.doesNotMatch(src, /Walk me through my tasks\."/);
  assert.match(start, /startLast\.current = msgs\.length \? msgs\[msgs\.length - 1\]\.id : null;\s*setStarting\(true\);/);
  assert.match(src, /const walkDots = starting && \(msgs\.length \? msgs\[msgs\.length - 1\]\.id : null\) === startLast\.current;/);
  assert.match(src, /\{\(busy \|\| phoneBusy \|\| nextComing \|\| walkDots\) && \(\s*<div className="tq-msg tq-pending">/);
  // ...and the welcome steps aside while it starts, as it did under the old line, coming back with its button if the start fails
  assert.match(src, /state && !shown\.length && !busy && !starting && welcome\(\)/);
});

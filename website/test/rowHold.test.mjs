// THE ROW WAITS FOR ITS DECISION (the dead-end walk's STILL, 2026-10-23): the rule lights a button on every item now, and a row drawn
// before its decision landed reshuffled under the owner's hand - a lit verb kept in view pushed its neighbour into the ▾ (an invite's
// Decline, a waiting task's Hand it to a person). The desk's row is held, room kept and nothing shown, until the item's FIRST decision
// is drawn - at most HOLD_MS - and a decision that lights nothing on purpose leaves a mark the walk can tell from a missing one.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the row is held - its room kept, aria-busy - only while the item's first decision is read, and never longer than HOLD_MS", () => {
  const row = src("ActionRow.jsx"), view = src("AssistantView.jsx");
  assert.match(row, /ActionRow\(\{ inline = false, advised = null, hold = false \}\)/);
  assert.match(row, /aria-busy=\{hold \|\| undefined\} style=\{hold \? \{ visibility: "hidden" \} : undefined\}/);
  assert.match(view, /const HOLD_MS = \d{3};/);
  assert.match(view, /setTimeout\(\(\) => setReading\(\(r\) => \(r === key \? "" : r\)\), HOLD_MS\)/, "a slow read never hides the row for good");
  assert.match(view, /<ActionRow advised=\{stripPick \|\| setupLit\} hold=\{!!reading && reading === onTable\} \/>/);
  // ...and nothing says it is reading: the strip that carried a "busy" attribute is gone (the owner, 2026-10-26: "remove the advisor")
  assert.doesNotMatch(view, /data-tq-strip=/);
});

test("a decision that lights nothing on purpose leaves a hidden mark, never a word", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /advice\?\.state && !advice\.verb && !advice\.none && <div hidden data-tq-advice="" data-tq-silent="" data-tq-unlit=\{advice\.state\} \/>/);
});

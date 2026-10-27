// THE ROW WAITS FOR ITS DECISION (the dead-end walk's STILL, 2026-10-23): the rule lights a button on every item now, and a row drawn
// before its decision landed reshuffled under the owner's hand - a lit verb kept in view pushed its neighbour into the ▾ (an invite's
// Decline, a waiting task's Hand it to a person). A decision that lights nothing on purpose leaves a mark the walk can tell from a missing one.
// ...AND IT DRAWS ONCE (the owner, 2026-10-27: "there were no buttons on the bottom, then it reloaded the buttons"): the wait hid the row
// (visibility) - an empty bar between two full ones. The row the owner was looking at stays drawn while the new one is not whole
// (actionRow.useRowHold), and the new one comes up in one step; browser/row-draws-once.test.mjs records it per frame.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ROW_HOLD_MS, rowDrawable, rowReady, sameRow } from "../src/actionRow.js";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the row is whole when the item's verbs are up, the walk move is over and the Advisor's read after the last press is in", () => {
  const list = [{ id: "next" }, { id: "reply", at: "b" }];
  assert.equal(rowReady({}), true, "nothing on the table, nothing left: nothing to wait for");
  assert.equal(rowReady({ leaving: "a" }), false, "a press leaving an item with nothing up yet waits");
  assert.equal(rowReady({ key: "a", leaving: "a", read: { key: "a" }, list: [{ id: "x", at: "a" }] }), false, "the item being left is not the new one");
  assert.equal(rowReady({ key: "b", read: { key: "b" }, list }), true);
  assert.equal(rowReady({ key: "b", read: { key: "b" }, list, moving: true }), false, "the walk move's answer still decides what is lit");
  assert.equal(rowReady({ key: "b", read: { key: "a" }, list }), false, "the Advisor's read is the last item's");
  assert.equal(rowReady({ key: "b", read: { key: "b", round: 1 }, list, round: 2 }), false, "a read made before the last press");
  assert.equal(rowReady({ key: "b", read: { key: "b", round: 2 }, list, round: 2 }), true);
  assert.equal(rowReady({ key: "b", read: { key: "b" }, list: [{ id: "next" }, { id: "send", at: "a" }] }), false, "another item's verbs are not this one's row");
  // ...and what the wait may give way to: the item's own verbs, never a lone Next between two items
  assert.equal(rowDrawable({ key: "b", list: [{ id: "floor:next" }] }), false, "the floor's Next is no item's row");
  assert.equal(rowDrawable({ key: "r", list: [{ id: "next" }, { id: "w:mine" }], keyed: false }), true, "a report's card registers no key: its verbs are the row");
  assert.equal(rowDrawable({ key: "r", list: [{ id: "next" }, { id: "w:mine" }] }), false, "a task's are keyed: none yet is no row");
  assert.equal(rowDrawable({ key: "b", list }), true);
  assert.ok(ROW_HOLD_MS > 0 && ROW_HOLD_MS <= 600);
});

test("the held row follows the live one only for the same buttons of the same item", () => {
  const a = { list: [{ id: "reopen", label: "Reopen task", at: "t" }] }, busy = { list: [{ id: "reopen", label: "Reopening…", disabled: true, at: "t" }] };
  assert.ok(sameRow(a, busy), "a label turned to its busy word is the same row");
  assert.ok(!sameRow(a, { list: [{ id: "reopen", at: "u" }] }), "the same verb of another item is not");
  assert.ok(!sameRow(a, { list: [{ id: "done", at: "t" }] }));
});

test("the row is never hidden while it waits: the old one stays up, and the hold is the page's", () => {
  const row = src("ActionRow.jsx"), view = src("AssistantView.jsx");
  assert.doesNotMatch(row, /visibility: "hidden"/);
  assert.match(row, /ActionRow\(\{ inline = false, advised: given = null, hold = false, early = true \}\)/);
  assert.match(view, /<ActionRow advised=\{stripPick \|\| setupLit\} hold=\{rowHold\} early=\{rowEarly\} \/>/);
  assert.doesNotMatch(view, /HOLD_MS = \d+;|setReading/, "no timer of its own hides the row");
  // ...and nothing says it is reading: the strip that carried a "busy" attribute is gone (the owner, 2026-10-26: "remove the advisor")
  assert.doesNotMatch(view, /data-tq-strip=/);
});

test("a decision that lights nothing on purpose leaves a hidden mark, never a word", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /advice\?\.state && !advice\.verb && !advice\.none && <div hidden data-tq-advice="" data-tq-silent="" data-tq-unlit=\{advice\.state\} \/>/);
});

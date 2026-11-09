// THE ROW WAITS FOR ITS DECISION (the dead-end walk's STILL, 2026-10-23): the rule lights a button on every item now, and a row drawn
// before its decision landed reshuffled under the owner's hand - a lit verb kept in view pushed its neighbour into the ▾ (an invite's
// Decline, a waiting task's Hand it to a person). A decision that lights nothing on purpose leaves a mark the walk can tell from a missing one.
// ...AND IT DRAWS ONCE (the owner, 2026-10-27: "there were no buttons on the bottom, then it reloaded the buttons"): the wait hid the row
// (visibility) - an empty bar between two full ones. The row the owner was looking at stays drawn while the new one is not whole
// (actionRow.useRowHold), and the new one comes up in one step; browser/row-draws-once.test.mjs records it per frame.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ROW_HOLD_MS, heldOff, heldRow, rowDrawable, rowReady, sameRow } from "../src/actionRow.js";

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

// THE OWNER, 2026-11-09: "I thought it's greyed out until you can click it again" - a second Mark done while the next task loaded did nothing
test("a held button that would do nothing is greyed, and un-greys the moment a press works again", () => {
  const kept = { list: [{ id: "next", group: "next", label: "Next" }, { id: "done", group: "more", label: "Mark done", at: "a" }, { id: "nope", group: "more", at: "a" }] };
  const loading = { list: [{ id: "next", group: "next", label: "Next", disabled: true }] };
  const { verbs, liveOf } = heldRow(kept, loading), by = (id) => verbs.list.find((v) => v.id === id);
  assert.ok(by("done").disabled && by("done").inert, "the left task's Mark done has no live verb: greyed, marked inert");
  assert.ok(by("next").disabled && !by("next").inert, "Next greys until the move lands - the live one is greyed");
  assert.equal(liveOf("done"), undefined, "...and its press runs nothing, as it looks");
  // the next task's verbs arrive while the old row is still held: the same id for another item is still not this button's
  const half = { list: [{ id: "next", group: "next" }, { id: "done", group: "more", at: "b" }] };
  assert.ok(heldRow(kept, half).verbs.list.find((v) => v.id === "done").disabled, "another item's Mark done does not wake the left one's");
  assert.ok(!heldRow(kept, half).verbs.list.find((v) => v.id === "next").disabled, "Next is live once the move has landed");
  // the item still on the table: its held buttons act, so they stand live; a live verb greyed greys the held one
  const same = { list: [{ id: "next", group: "next" }, { id: "done", group: "more", at: "a" }, { id: "nope", group: "more", at: "a", disabled: true }] };
  const h = heldRow(kept, same).verbs.list;
  assert.ok(!h.find((v) => v.id === "done").disabled && heldRow(kept, same).liveOf("done"), "the same item's Mark done works, so it is not greyed");
  assert.ok(h.find((v) => v.id === "nope").disabled, "a held button whose live one is greyed is greyed");
  assert.equal(heldRow(same, same).verbs, same, "released: the live row itself, nothing greyed by the hold");
  assert.ok(heldOff(verbs.list.filter((v) => v.group === "more")) && !heldOff(h.filter((v) => v.group === "more")) && !heldOff([]), "a ▾ of held moves greys with them");
  assert.ok(src("ActionRow.jsx").includes("aria-disabled={v.disabled || undefined}"), "a greyed button says so to a reader too");
});

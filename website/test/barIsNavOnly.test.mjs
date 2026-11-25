// THE BAR UNDER THE CHAT IS NAVIGATION ONLY (the owner, 2026-11-10, over an FYI batch whose bar read Back, All read next and a CHANGE pill
// holding an idea's "No more ideas like this": "who asked you to add this to fyi??? on bottom the only buttons should be nav. all other
// buttons should be on task no????"). Back and Next stand on the desk's bar; every other move rides the item's own row (ItemMoves) - and with
// nothing on the table, the one exception that day: the sidebar's New and Change my setup.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { rowOf, splitRow } from "../src/actionRow.js";
import { hasCorrespondent } from "../src/taskLifecycle.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const ids = (r) => [...r.decide, ...r.agent, ...r.more].map((x) => x.id);

test("an FYI batch on the desk: its bar is Back and All read, next - a stray move goes to the item's own row, never the bar", () => {
  // the live shape: the batch lays no panes (ItemSections lays={!batch}), its Foot's All read, next is the row's Next, and a line's chip
  // registered beside it - before, it stood on the bar in a CHANGE pill
  const list = [v("next", "next", { label: "All read, next" }), v("back", "back", { label: "Back" }), v("chat:not_ours_kind", "decide", { label: "No more ideas like this" })];
  const before = splitRow(rowOf({ ref: "", list }), null);
  assert.deepEqual(ids(before.row), ["chat:not_ours_kind"], "a phone's own row (not the desk's bar) keeps every move, as it did");
  const { row, by } = splitRow(rowOf({ ref: "", list }), null, true);
  assert.deepEqual(ids(row), [], "nothing but Back and Next on the desk's bar");
  assert.equal(row.next.label, "All read, next");
  assert.ok(row.back);
  assert.deepEqual(by.item.map((x) => x.id), ["chat:not_ours_kind"], "the move is the item's, on its own row");
});

test("nothing on the table: Back, New and Change my setup - New is the sidebar's own door, and Set something up is gone", () => {
  const list = [v("back", "back"), v("chat:newtask", "decide", { label: "New", bar: true }), v("chat:tour", "decide", { label: "Change my setup", bar: true }),
    v("chat:walk", "decide", { label: "Walk me through my tasks" })];
  const { row, by } = splitRow(rowOf({ ref: "", list }), null, true);
  assert.deepEqual(ids(row), ["chat:newtask", "chat:tour"]);
  assert.deepEqual(by.item.map((x) => x.id), ["chat:walk"], "anything else is drawn on the line it belongs to");
  const view = read("AssistantView.jsx");
  assert.match(view, /const NEW_DOOR = SIDE_NAV\.find\(\(n\) => n\.key === "new"\);/);
  assert.match(view, /const IDLE_CHIPS = \[\{ verb: "newtask", label: NEW_DOOR\.label, hint: NEW_DOOR\.hint, bar: true \}, \{ verb: "tour", label: "Change my setup", bar: true \}\];/);
  assert.doesNotMatch(view, /setupask/, "no separate Set something up: New leads to it");
});


test("a task's row: the server's ReadsReply decides, a machine's notice on email included", () => {
  assert.equal(hasCorrespondent({ Channel: "email", FromOwner: false, ReadsReply: false }), false, "a code host's notice: no Reply");
  assert.equal(hasCorrespondent({ Channel: "email", FromOwner: false, ReadsReply: true }), true);
  assert.equal(hasCorrespondent({ Channel: "own", FromOwner: false }), false, "a row from before the field still reads its channel");
});

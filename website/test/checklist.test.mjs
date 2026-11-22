import test from "node:test";
import assert from "node:assert/strict";

import { checklistMarkdown, parseChecklist, toggleItem, progressLine, settleTick, withTicks } from "../src/checklist.js";

// PW-075/PW-077: one list, GitHub task-list syntax, shared by the task page and the assistant card;
// ticking boxes is progress on the list, never task completion.

const ITEMS = [{ id: "a1", text: "Add Priya to the payroll portal", done: true }, { id: "b2", text: "Send Dana the August export", done: false }];

test("items render as GitHub task-list markdown and parse back", () => {
  const md = checklistMarkdown(ITEMS);
  assert.equal(md, "- [x] Add Priya to the payroll portal\n- [ ] Send Dana the August export");
  assert.deepEqual(parseChecklist(md).map((i) => [i.text, i.done]), [["Add Priya to the payroll portal", true], ["Send Dana the August export", false]]);
  assert.deepEqual(parseChecklist(""), []);
});

test("toggling flips one item by id and leaves the rest", () => {
  const next = toggleItem(ITEMS, "b2");
  assert.deepEqual(next.map((i) => i.done), [true, true]);
  assert.deepEqual(ITEMS.map((i) => i.done), [true, false]);              // no mutation
  assert.deepEqual(toggleItem(ITEMS, "zz"), ITEMS);
});

test("the progress line counts boxes and never calls the task done", () => {
  assert.equal(progressLine(ITEMS), "1 of 2 done");
  assert.equal(progressLine([{ id: "x", text: "t", done: true }]), "1 of 1 done — Mark done when it is really finished");
  assert.equal(progressLine([]), "");
});


// A TICK DRAWS AT THE CLICK (the owner, 2026-10-20: about a second to respond - three round trips before the box moved)
test("a press in flight is drawn over the server's list, and settles only when no newer press replaced it", () => {
  assert.deepEqual(withTicks(ITEMS, { b2: true }).map((i) => i.done), [true, true]);
  assert.deepEqual(withTicks(ITEMS, {}), ITEMS);
  assert.deepEqual(withTicks(undefined, { b2: true }), []);
  assert.deepEqual(settleTick({ b2: true, a1: false }, "b2", true), { a1: false }, "its answer is in: the server's list speaks");
  const newer = { b2: false };
  assert.equal(settleTick(newer, "b2", true), newer, "a second press on the box is still in flight: it stays drawn");
});

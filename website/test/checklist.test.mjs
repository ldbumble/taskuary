import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { checklistMarkdown, parseChecklist, toggleItem, progressLine } from "../src/checklist.js";

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
  assert.equal(progressLine([{ id: "x", text: "t", done: true }]), "1 of 1 done — close the task when it is really finished");
  assert.equal(progressLine([]), "");
});

test("the task page and the assistant card render the shared list", () => {
  for (const f of ["TasksView.jsx", "assistantCards.jsx"]) {
    const src = readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
    assert.match(src, /from "\.\/checklist\.js"/, `${f} uses the shared checklist helpers`);
  }
});

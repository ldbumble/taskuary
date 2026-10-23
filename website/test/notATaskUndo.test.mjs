import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { announceRemoved, clearRemoved, fromAnswer, lastRemoved, removedLine, showsRemoved } from "../src/removed.js";

// REMOVE - NOT A TASK IS TAKEN BACK IN PLACE (the owner, 2026-10-21: act at once + Undo; the task card had none, 2026-10-22): the
// server keeps the task (recentlydeleted.keep_task) and answers {deleted, title, kind: "task"}; the page announces it, and the lists
// the task leaves - the rail and the Tasks list - draw "Removed <title> - Undo", Undo restoring it.
const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the server's answer to Remove - not a task is the Undo line's", () => {
  const r = announceRemoved(fromAnswer({ ok: true, deleted: 41, title: "Fuel card statement", kind: "task" }, "task", "x"));
  assert.deepEqual([r.did, r.title, r.kind], [41, "Fuel card statement", "task"]);
  assert.equal(lastRemoved(), r);
  assert.ok(showsRemoved(r, ["task"])); assert.ok(!showsRemoved(r, ["report"]), "only a list that holds tasks draws it");
  assert.equal(removedLine(r.title, r.verb), "Removed Fuel card statement");
  clearRemoved(41); assert.equal(lastRemoved(), null);
});

test("the task page announces the Remove, and the rail and the Tasks list draw its Undo", () => {
  const page = read("TaskPage.jsx");
  assert.match(page, /try \{ out = await runOperation\(api, "task\.not_a_task", selected\); \}/);
  assert.match(page, /announceRemoved\(fromAnswer\(out, "task", t\?\.Title \|\| "the task"\)\);/);
  assert.match(read("AssistantView.jsx"), /top=\{<><UndoLine kinds=\{\["task"\]\} onRestored=\{\(\) => \{ loadPile\(true\); onChanged\?\.\(\); \}\}/);
  assert.match(read("TasksView.jsx"), /<UndoLine kinds=\{\["task"\]\} onRestored=\{\(\) => \{ loadTasks\(\); onChanged\?\.\(\); \}\}/);
});

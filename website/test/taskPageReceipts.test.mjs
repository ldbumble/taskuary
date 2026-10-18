// EVERY PRESS LEAVES A RECEIPT (Stream B, the owner 2026-10-18): the task page's owner acts run down the task tools' road
// (taskOps.runOperation) - recorded, said in the chat when the task is on the Assistant's table, and offered back there - never
// the endpoint underneath. A press on the table's task view brings its Take it back onto the bar (freshUndo, UndoVerb).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { freshUndo } from "../src/assistantTurns.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("the task page's owner acts are the task tools, not the endpoints under them", () => {
  const page = read("TaskPage.jsx"), reshape = read("Reshape.jsx");
  for (const kind of ["task.update", "task.set_kind", "task.check", "task.checklist", "task.comment", "task.not_a_task", "task.clarify", "task.trust"])
    assert.match(page, new RegExp(`(runOperation\\(api, |op\\(|change\\()"${kind.replace(".", "\\.")}"`), kind);
  for (const door of [/api\.patch\(`\/api\/tasks\/\$\{[^}]+\}`/, /\/checklist\/\$\{/, /api\.put\(`\/api\/tasks\/\$\{task\.TaskId\}\/checklist`/,
                      /\/comments`/, /\/not-a-task`/, /\/clarify`/, /\/trust`/])
    assert.doesNotMatch(page, door, String(door));
  assert.match(reshape, /runOperation\(api, "task\.split", taskId/);
  assert.match(reshape, /runOperation\(api, "task\.merge", src, \{ into: String\(dst\) \}\)/);
  assert.doesNotMatch(reshape, /\/split`|\/merge`, /);
});

test("the menus' unassigned is a change, and a blur that moved no day presses nothing", () => {
  const page = read("TaskPage.jsx");
  assert.match(page, /change\("task\.update", \{ assignee: v \|\| "none" \}\)/);
  const move = page.slice(page.indexOf("const moveDate = async"), page.indexOf("const tick = async"));
  assert.ok(move.indexOf("return;") > -1 && move.indexOf("return;") < move.indexOf('op("task.update"'), "an unchanged day returns first");
});

test("a box is named by its own id as well as its number", () => {
  const page = read("TaskPage.jsx");
  assert.match(page, /runOperation\(api, "task\.check", t\.TaskId, \{ item: String\(checklist\.indexOf\(i\) \+ 1\), id: i\.id, done: !i\.done \}\)/);
  assert.match(page, /op\("task\.check", \{ item: String\(steps\.indexOf\(s\) \+ 1\), id: s\.id, done: !s\.done \}/);
});

test("a task view's Take it back reaches the bar from a read that added it - never from history on a first load", () => {
  const undo = { id: 41, role: "assistant", text: "Done - Change the task · TQ-0007. Undo: Put priority back to normal.",
                 card: { kind: "proposal", op: "abc123", title: "Put priority back to normal", undo: true, background_event: true } };
  assert.deepEqual(freshUndo([{ id: 1 }], [undo]), { verb: "undo", op: "abc123", title: "Put priority back to normal" });
  assert.equal(freshUndo([], [undo]), null, "a first load reads history");
  // a chat's own undo keeps its card, live under it
  assert.equal(freshUndo([{ id: 1 }], [{ ...undo, card: { ...undo.card, background_event: undefined } }]), null);
  const view = read("AssistantView.jsx");
  assert.match(view, /const undo = freshUndo\(msgsRef\.current, mergeDurableTurns\(msgsRef\.current, st\.messages \|\| \[\]\)\.added\);/);
  assert.match(view, /if \(c\.verb === "undo" && c\.op\) \{[\s\S]{0,200}api\.get\(`\/api\/operations\/\$\{c\.op\}`\)[\s\S]{0,120}op\?\.status === "proposed"/);
});

test("the demo runs the page's task tools as its old doors did", () => {
  const demo = read("demoApi.js");
  for (const kind of ["task.update", "task.set_kind", "task.check", "task.defer"]) assert.match(demo, new RegExp(`"${kind.replace(".", "\\.")}": \\(t, p\\) =>`));
  assert.match(demo, /p === "\/api\/operations" && OP_DOORS\[body\?\.kind\]/);
});

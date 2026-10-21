// EVERY PRESS LEAVES A RECEIPT (Stream B, the owner 2026-10-18): the task page's owner acts run down the task tools' road
// (taskOps.runOperation) - recorded and said in the chat when the task is on the Assistant's table - never the endpoint underneath.
// No Take it back anywhere (the owner, 2026-10-19: "no take it back button. hate that"): a wrong Mark done is put right with Reopen task.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { mergeDurableTurns, oneCopy, placeLine } from "../src/assistantTurns.js";

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
  // the press is read at the click (drawn at once, sent in order): the number and the id are the box's as it was pressed
  assert.match(page, /const tid = t\.TaskId, done = !i\.done, item = String\(checklist\.indexOf\(i\) \+ 1\);/);
  assert.match(page, /runOperation\(api, "task\.check", tid, \{ item, id: i\.id, done \}\)/);
  assert.match(page, /op\("task\.check", \{ item: String\(steps\.indexOf\(s\) \+ 1\), id: s\.id, done: !s\.done \}/);
});

test("a task view's receipt is its line and nothing to take back", () => {
  const view = read("AssistantView.jsx");
  assert.doesNotMatch(view, /freshUndo|UndoVerb|setUndoOffer|verb === "undo"|take_back/);
  assert.doesNotMatch(read("proposalCard.js"), /_undo|take_back/);
  assert.doesNotMatch(read("RunSteps.jsx"), /undo-repair|take_back/);
});

// G3 of the 2026-10-19 UI walk: TQ-0010 stood five times in the chat, once per search, Board or rail pick
test("an item opened again is one line in the chat, at the end - and the server's copies of it stay folded in", () => {
  const item = (id, extra = {}) => ({ id, role: "assistant", text: "Erin Blake wants the May numbers", card: { kind: "task", key: "task:10" }, ...extra });
  const said = { id: "u1", role: "user", text: "what else?" };
  const once = placeLine([item("a1", { commentId: 7 }), said], item("a2"));
  assert.deepEqual(once.map((m) => m.id), ["u1", "a2"]);
  assert.deepEqual(once[1].alias, ["a1", 7]);
  // ...the history read back carries the old copy (7) and the new one (8): neither draws a second line
  const back = mergeDurableTurns(once, [item(7), item(8)]).messages;
  assert.equal(back.filter((m) => m.card?.key === "task:10").length, 1);
  // ...a first load of a history with the item three times draws it once, where it last stood
  const hist = oneCopy([item(1), said, item(2), item(3)]);
  assert.deepEqual(hist.map((m) => m.id), ["u1", 3]);
  // ...and a proposal is never an item copy
  const prop = { id: "p", role: "assistant", text: "Not ours?", proposal: { id: "x" }, card: { kind: "proposal", key: "task:10" } };
  assert.equal(placeLine([prop], item("a3")).length, 2);
  assert.match(read("AssistantView.jsx"), /setMsgs\(\(m\) => placeLine\(ahead \? m\.filter\(\(x\) => x\.id !== ahead\.id\) : m, \{ id, role: "assistant"/);
});

test("the demo runs the page's task tools as its old doors did", () => {
  const demo = read("demoApi.js");
  for (const kind of ["task.update", "task.set_kind", "task.check", "task.defer"]) assert.match(demo, new RegExp(`"${kind.replace(".", "\\.")}": \\(t, p\\) =>`));
  assert.match(demo, /p === "\/api\/operations" && OP_DOORS\[body\?\.kind\]/);
});

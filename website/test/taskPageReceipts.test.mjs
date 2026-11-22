// EVERY PRESS LEAVES A RECEIPT (Stream B, the owner 2026-10-18): the task page's owner acts run down the task tools' road
// (taskOps.runOperation) - recorded and said in the chat when the task is on the Assistant's table - never the endpoint underneath.
// No Take it back anywhere (the owner, 2026-10-19: "no take it back button. hate that"): a wrong Mark done is put right with Reopen task.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { mergeDurableTurns, oneCopy, placeLine } from "../src/assistantTurns.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");


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
  // ...the answer's line placed by placeLine - in the place of the row its press drew ahead, when it is that row (rule 7)
  assert.match(read("AssistantView.jsx"), /setMsgs\(\(m\) => placeLine\(below \? m\.filter\(\(x\) => x\.id !== below\.id\) : m, \{ id, role: "assistant"/);
});

// WHAT IS TYPED AND NOT SENT STAYS IN ITS TASK'S BOX, AND THE ARROW SENDS WHILE THE AGENT WORKS (the owner, 2026-11-10; agent walk 2: a reload
// lost a half-written line, and the send arrow stood grey over typed words for as long as the agent's turn ran - Enter held the line, the arrow did not)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { keepUnsent, unsent } from "../src/unsent.js";

const box = () => { const m = new Map(); return { m, getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) }; };
const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("typed words are kept per task and come back as typed", () => {
  const s = box();
  keepUnsent(7, "tell Erin Thursday works  ", s); keepUnsent(8, "second task", s);
  assert.equal(unsent(7, s), "tell Erin Thursday works  ");
  assert.equal(unsent(8, s), "second task");
  assert.equal(unsent(9, s), "");
});

test("a sent or emptied box keeps nothing", () => {
  const s = box();
  keepUnsent(7, "half a line", s); keepUnsent(7, "", s);
  assert.equal(unsent(7, s), ""); assert.equal(s.m.size, 0);
  keepUnsent(7, "half a line", s); keepUnsent(7, "   \n", s);
  assert.equal(s.m.size, 0, "spaces alone are not a line");
});

test("no task, no storage and a storage that refuses are all the box alone", () => {
  const s = box(), refuses = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("full"); }, removeItem() { throw new Error("blocked"); } };
  keepUnsent(null, "words", s); assert.equal(s.m.size, 0);
  assert.equal(unsent(null, s), "");
  assert.doesNotThrow(() => { keepUnsent(7, "words", refuses); keepUnsent(7, "", refuses); keepUnsent(7, "words", null); });
  assert.equal(unsent(7, refuses), ""); assert.equal(unsent(7, null), "");
});

test("both of a task's boxes keep them: the chat's composer and the box before its first agent", () => {
  const chat = src("GeneralWorkspace.jsx"), first = src("AgentSummary.jsx");
  assert.match(chat, /if \(!c\.getState\(\)\.text && unsent\(id\)\) c\.setText\(unsent\(id\)\);/, "put back into an empty box only");
  assert.match(chat, /return c\.subscribe\(\(\) => keepUnsent\(id, c\.getState\(\)\.text\)\);/);
  assert.match(first, /useState\(\(\) => unsent\(task\.TaskId\)\)/);
  assert.match(first, /else keepUnsent\(task\.TaskId, text\);/);
});

test("words sent from the box before the first agent are not kept: the chat that draws next finds its box empty", () => {
  // the recorded walk, 2026-11-11: his first line stood in his bubble AND in the box under it, and his next line went out glued to it
  const first = src("AgentSummary.jsx"), send = first.slice(first.indexOf("const send = async () => {"));
  const cleared = send.indexOf('keepUnsent(task.TaskId, "");'), posted = send.indexOf("await api.post(`/api/tasks/${task.TaskId}/dispatch`");
  assert.ok(cleared > 0 && cleared < posted, "cleared at the press, before the start is asked for");
  assert.match(send, /catch \(e\) \{ keepUnsent\(task\.TaskId, text\);/, "a start that failed keeps them");
});

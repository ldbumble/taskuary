import test from "node:test";
import assert from "node:assert/strict";

import { noteKey, noteOf, notePath, saveNote } from "../src/checklist.js";

// A NOTE ON ONE TO-DO (the owner, 2026-10-20): kept with the box, shown under its words, edited inline - no dialog.

test("a note is the box's own, trimmed, and absent is none", () => {
  assert.equal(noteOf({ id: "a", text: "send the W-9", note: "  Paula has it " }), "Paula has it");
  assert.equal(noteOf({ id: "a", text: "send the W-9" }), "");
});

test("it saves to the box's own route, and an empty field takes it off", async () => {
  const sent = [];
  const api = { patch: async (p, b) => { sent.push([p, b]); return { data: { ok: true } }; } };
  await saveNote(api, 12, "ab12", " Paula has it ");
  await saveNote(api, 12, "ab12", "   ");
  assert.deepEqual(sent, [["/api/tasks/12/checklist/ab12/note", { note: "Paula has it" }], ["/api/tasks/12/checklist/ab12/note", { note: "" }]]);
  assert.equal(notePath(3, "a/b"), "/api/tasks/3/checklist/a%2Fb/note");
});

test("Enter saves, Escape leaves it as it was, anything else types", () => {
  const did = [];
  const ev = (key, shiftKey = false) => ({ key, shiftKey, preventDefault() {} });
  const h = { save: () => did.push("save"), cancel: () => did.push("cancel") };
  assert.equal(noteKey(ev("Enter"), h), true);
  assert.equal(noteKey(ev("Escape"), h), true);
  assert.equal(noteKey(ev("a"), h), false);
  assert.equal(noteKey(ev("Enter", true), h), false);
  assert.deepEqual(did, ["save", "cancel"]);
});

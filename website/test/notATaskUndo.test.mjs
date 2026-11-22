import test from "node:test";
import assert from "node:assert/strict";

import { announceRemoved, clearRemoved, fromAnswer, lastRemoved, removedLine, showsRemoved } from "../src/removed.js";


test("the server's answer to Not a task is the Undo line's", () => {
  const r = announceRemoved(fromAnswer({ ok: true, deleted: 41, title: "Fuel card statement", kind: "task" }, "task", "x"));
  assert.deepEqual([r.did, r.title, r.kind], [41, "Fuel card statement", "task"]);
  assert.equal(lastRemoved(), r);
  assert.ok(showsRemoved(r, ["task"])); assert.ok(!showsRemoved(r, ["report"]), "only a list that holds tasks draws it");
  assert.equal(removedLine(r.title, r.verb), "Removed Fuel card statement");
  clearRemoved(41); assert.equal(lastRemoved(), null);
});

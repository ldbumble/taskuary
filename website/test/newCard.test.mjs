import test from "node:test";
import assert from "node:assert/strict";


import { planTask } from "../src/newTask.js";


test("the chosen repository becomes the new task's repo tag, and a chat has none", () => {
  assert.match(planTask("northwind/ledger", "terminal", false, true).tags, /repo:northwind\/ledger/);
  assert.equal(planTask(null, "terminal", false, true).tags, "stay:open");                 // auto, nothing named: no tag
  assert.equal(planTask(null, "terminal", false, true).kind, "coding");
});

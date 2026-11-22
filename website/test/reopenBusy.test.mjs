// REOPEN IS BUSY AT THE PRESS AND OPEN AT THE ANSWER (the owner, 2026-10-23: "when you hit reopen task nothing happens for a few
// seconds"): the page redrew only when the follow-up read of the task came back, with nothing on the button meanwhile.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { pageState, reopenedDetail } from "../src/taskLifecycle.js";

const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");


test("the reopened detail is open, its reminder cleared, an owner's close read as on you", () => {
  const d = { task: { TaskId: 7, Status: "done", RemindAt: "2026-11-01" }, state: "closed", closedWhy: "Closed." };
  const o = reopenedDetail(d);
  assert.deepEqual([o.task.Status, o.task.RemindAt, o.state, o.closedWhy], ["open", "", "yours", null]);
  assert.equal(reopenedDetail({ task: { Status: "done" }, state: "agentdone" }).state, "agentdone");
  assert.equal(d.task.Status, "done", "the old detail is not changed in place");
});

test("a list row still saying closed does not put a reopened page back to closed", () => {
  const open = reopenedDetail({ task: { Status: "done" }, state: "closed" });
  assert.equal(pageState({ State: "closed" }, open), "yours");
  assert.equal(pageState({ State: "agentdone" }, open), "agentdone");
  assert.equal(pageState({ State: "closed" }, { task: { Status: "done" }, state: "agentdone" }), "closed", "a closed task's row still wins");
});

// REOPEN IS BUSY AT THE PRESS AND OPEN AT THE ANSWER (the owner, 2026-10-23: "when you hit reopen task nothing happens for a few
// seconds"): the page redrew only when the follow-up read of the task came back, with nothing on the button meanwhile.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { pageState, reopenedDetail } from "../src/taskLifecycle.js";

const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
const body = (head) => { const i = page.indexOf(head); assert.ok(i >= 0, `${head} is there`); return page.slice(i, page.indexOf("\n  };", i)); };

test("Reopen goes busy before the request, and a second press while busy does nothing", () => {
  const f = body("const reopen = async () => {");
  const busy = f.indexOf("setReopening(id)"), ask = f.indexOf('runOperation(api, "task.reopen"');
  assert.ok(busy >= 0 && ask > busy, "busy is set before the operation is sent");
  assert.match(f, /if \(!id \|\| reopening === id\) return;/);
});

test("the page opens at the server's answer, before the re-reads; a failure says so the way other presses do", () => {
  const f = body("const reopen = async () => {");
  assert.ok(f.indexOf("reopenedDetail(d)") < f.indexOf("loadDetail(id)"), "drawn open before the detail is read again");
  assert.doesNotMatch(f, /await load/, "the re-reads are not waited on");
  assert.match(f, /catch \(e\) \{ setReopening\(null\); if \(!stale\(id\)\) setErr\(opError\(e,/);
});

test("both Reopen buttons are disabled and say Reopening… while it is on its way", () => {
  const row = page.slice(page.indexOf('[{ id: "reopen"'), page.indexOf("}]", page.indexOf('[{ id: "reopen"')));
  assert.match(row, /label: reopening === selected \? "Reopening…"/);
  assert.match(row, /disabled: reopening === selected/);
  const bar = page.slice(page.indexOf('<Button size="small" variant="outlined" disabled={reopening === selected}'), page.indexOf('labelOfRow("reopen")}</Button>'));
  assert.match(bar, /<CircularProgress size=\{11\} \/>/);
  assert.match(bar, /"Reopening…"/);
});

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

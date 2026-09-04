import test from "node:test";
import assert from "node:assert/strict";
import { completionTransition, filterForSelectedState, nextTaskId } from "../src/taskFilter.js";

test("a selected task that finishes moves the rail from in progress to done", () => {
  assert.equal(filterForSelectedState("live", "done"), "done");
});

test("a selected active task reopened from done moves the rail back to in progress", () => {
  assert.equal(filterForSelectedState("done", "working"), "live");
  assert.equal(filterForSelectedState("done", "needs_you"), "live");
});

test("all and matching buckets are left alone", () => {
  assert.equal(filterForSelectedState("", "done"), "");
  assert.equal(filterForSelectedState("live", "working"), "live");
  assert.equal(filterForSelectedState("done", "done"), "done");
});

test("mark done advances to the next in-progress task and never back to the closed task", () => {
  assert.equal(nextTaskId([358, 356, 367], 358), 356);
  assert.equal(nextTaskId([358, 356, 367], 356), 367);
  assert.equal(nextTaskId([358, 356, 367], 367), 356);
  assert.equal(nextTaskId([358], 358), null);
  assert.equal(nextTaskId([356, 367], 358), 356);
  assert.deepEqual(completionTransition([358, 356, 367], 358), {
    next: 356,
    filter: "live",
    seen: { id: 358, key: "done" },
  });
});

test("the Tasks completion path pins the rail to in progress before patching", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("../src/TasksView.jsx", import.meta.url), "utf8");
  const start = source.indexOf("const finish = async (status)");
  const finish = source.slice(start, source.indexOf("const firstShownId", start));
  assert.match(finish, /filter\(\(x\) => inBucket\(x, "live"\)\)/);
  assert.match(finish, /completionTransition\(liveIds, selected, status\)/);
  assert.ok(finish.indexOf("setFilter(transition.filter)") < finish.indexOf("await api.patch"));
  assert.ok(finish.indexOf("onSelect(transition.next)") > finish.indexOf("await api.patch"));
});

test("a closed task opened directly cannot remain under the in-progress pill", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("../src/TasksView.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /was\.id !== selected \|\| was\.key === key/);
  assert.match(source, /if \(was\.id === selected && was\.key === key\) return/);
  assert.match(source, /onChange=\{changeFilter\}/);
  assert.match(source, /inBucket\(row, next\)/);
  assert.match(source, /onSelect\(replacement\)/);
});

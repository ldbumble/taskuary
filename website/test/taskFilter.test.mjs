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
  // completion runs the shared operations road now (PW-215); the pin is the ordering around that call
  assert.ok(finish.indexOf("setFilter(transition.filter)") < finish.indexOf('await runOperation(api, "task.complete"'));
  assert.ok(finish.indexOf("onSelect(transition.next)") > finish.indexOf('await runOperation(api, "task.complete"'));
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

// The X on the task detail cleared the selection, and the "follow the list to its first row"
// effect put the same task straight back - a flicker that landed you where you started (the owner,
// 2026-09-18: "when you hit x when coding to see task it just flickers and comes back").
test("closing the detail shows the list rather than re-opening the first task", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("../src/TasksView.jsx", import.meta.url), "utf8");
  assert.match(source, /const dismiss = \(\) => \{ dismissed\.current = true; onSelect\(null\); \}/);
  assert.match(source, /if \(active && !selected && firstShownId && !dismissed\.current\) onSelect\(firstShownId\)/);
  assert.match(source, /Close — back to the list \(the task stays\)"\}>\s*<IconButton size="small" onClick=\{\(\) => \(sessionView \? setPeek\(true\) : dismiss\(\)\)\}/);
  assert.match(source, /if \(selected \|\| !active\) dismissed\.current = false/, "a real pick, or leaving the tab, lifts it");
});

// "even if the coding cli is open i want to be able to go back to see the actual task and where it
// came from" (the owner, 2026-09-18). One X, two steps: session -> the task behind it -> the list.
test("with a live session, X steps back to the task first and the session keeps running", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("../src/TasksView.jsx", import.meta.url), "utf8");
  assert.match(source, /const sessionView = liveSession && !peek;/);
  assert.match(source, /useEffect\(\(\) => \{ if \(!liveSession\) setPeek\(false\); \}, \[liveSession\]\);/, "the session ending puts the page back");
  assert.match(source, /workspaceMode === "live" && peek \?/, "the terminal folds to a line instead of unmounting the page");
  assert.match(source, /Back to the session/);
  // the task card, the reply card, context & history and earlier runs all come back while peeking
  for (const gate of [/\{!sessionView && \(\s*<Box sx=\{\{ \.\.\.card, mb: 1\.25/, /\{!sessionView && <Fold title=\{`Context & history/,
    /\{!sessionView && detail\.runs\.length > 0/, /\{!sessionView && <Box sx=\{\{ \.\.\.card, mt: 1\.25, p: stage === "reply"/]) {
    assert.match(source, gate);
  }
  assert.doesNotMatch(source, /\{!term\?\.alive && <Fold title=\{`Context & history/, "no gate left on the raw flag");
});

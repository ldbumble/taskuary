import { taskSource } from "./taskSource.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import {
  completionTransition,
  cutAway,
  filterForSelectedState,
  localStamp,
  nextTaskId,
  remindDay,
  remindWaiting,
} from "../src/taskFilter.js";

// in progress / upcoming / done - one pill per task, no "all" (the owner, 2026-09-25)
test("a selected task that finishes moves the rail from in progress to done", () => {
  assert.equal(filterForSelectedState("live", "done"), "done");
});

test("a task put away with Remind me follows into upcoming, and back when it returns", () => {
  assert.equal(filterForSelectedState("live", "upcoming"), "upcoming");
  assert.equal(filterForSelectedState("upcoming", "working"), "live");
  assert.equal(filterForSelectedState("upcoming", "done"), "done");
});

test("a task reopened under done goes back to in progress; dropped has no pill and moves nothing", () => {
  assert.equal(filterForSelectedState("done", "working"), "live");
  assert.equal(filterForSelectedState("done", "upcoming"), "upcoming");
  assert.equal(filterForSelectedState("live", "dropped"), "live");
});

test("matching buckets are left alone", () => {
  assert.equal(filterForSelectedState("done", "done"), "done");
  assert.equal(filterForSelectedState("live", "working"), "live");
  assert.equal(filterForSelectedState("upcoming", "upcoming"), "upcoming");
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
  const source = taskSource();
  // the list pins (TasksView.finishWith) around the close the task view runs (TaskPage.finish -> the shared road, PW-215)
  const start = source.indexOf("const finishWith = async (status, close)");
  const finish = source.slice(start, source.indexOf("const reminded", start));
  assert.match(finish, /filter\(\(x\) => inBucket\(x, "live"\)\)/);
  assert.match(finish, /completionTransition\(liveIds, selected, status\)/);
  assert.ok(finish.indexOf("setFilter(transition.filter)") < finish.indexOf("await close()"));
  // PUT DOWN AT THE PRESS (2026-10-02: "the task stays open for a 2 count then closes"): the next task opens and this one
  // leaves the list BEFORE the close; a close that fails puts it back
  assert.ok(finish.indexOf("onSelect(transition.next)") < finish.indexOf("await close()"));
  assert.ok(finish.indexOf("setLeavingId(was)") < finish.indexOf("await close()"));
  assert.match(finish, /catch \(e\) \{ seenState\.current = before; setLeavingId\(null\); onSelect\(was\); throw e; \}/);
  assert.match(source, /\.filter\(\(x\) => x\.TaskId !== leavingId\)/);
  const page = source.slice(source.indexOf("const finish = async (status)"));
  assert.match(page.slice(0, 600), /const close = \(\) => runOperation\(api, "task\.complete", selected\)/);
  assert.match(page.slice(0, 600), /onFinish \? onFinish\(status, close\) : close\(\)/);
});

test("a closed task opened directly cannot remain under the in-progress pill", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = taskSource();
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
  const source = taskSource();
  assert.match(source, /const dismiss = \(\) => \{ dismissed\.current = true; onSelect\(null\); \}/);
  assert.match(source, /if \(active && !selected && firstShownId && !dismissed\.current\) onSelect\(firstShownId\)/);
  assert.match(source, /Close — back to the list \(the task stays\)"\}>/);
  assert.match(source, /<IconButton aria-label=\{sessionView \? "Back to task" : "Close task"\} size="small" onClick=\{\(\) => \(sessionView \? setPeek\(true\) : dismiss\(\)\)\}/);
  assert.match(source, /if \(selected \|\| !active\) dismissed\.current = false/, "a real pick, or leaving the tab, lifts it");
});

// "even if the coding cli is open i want to be able to go back to see the actual task and where it
// came from" (the owner, 2026-09-18). One X, two steps: session -> the task behind it -> the list.
test("with a live session, X steps back to the task first and the session keeps running", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = taskSource();
  assert.match(source, /const sessionView = liveSession && !peek;/);
  // ...and it drops a hand-picked stage with it, so the reply the wrap-up just wrote is what the
  // page opens on rather than the pane that has finished (2026-09-22)
  assert.match(source, /if \(!liveSession\) \{ setPeek\(false\); setOpenStage\(null\); \}/, "the session ending puts the page back");
  assert.match(source, /workspaceMode === "live" && peek \?/, "the terminal folds to a line instead of unmounting the page");
  assert.match(source, /Back to the session/);
  // the task card, the reply card, context & history and earlier runs all come back while peeking
  for (const gate of [/\{!sessionView && \(\s*<Box sx=\{\{ \.\.\.card, mb: 1\.25/, /\{!sessionView && <Fold title=\{`Context & history/,
    /\{!sessionView && detail\.runs\.length > 0/, /\{!sessionView && <Box sx=\{\{ \.\.\.card, mt: 1\.25, p: stage === "reply"/]) {
    assert.match(source, gate);
  }
  assert.doesNotMatch(source, /\{!term\?\.alive && <Fold title=\{`Context & history/, "no gate left on the raw flag");
});

// THE CUT BELONGS TO THE ROW. Applying it per pill gave `in progress` a wider window than `all`
// (live work of any age vs today only), so "all 5" sat over "in progress 4 · done 2" and the
// arithmetic could not close (the owner, 2026-09-22: "that doesn't add up?").
test("live work shows at any age; finished work stops at today", () => {
  assert.equal(cutAway("needs_you", false, false), false);   // live, last touched yesterday - still live
  assert.equal(cutAway("working", false, false), false);
  assert.equal(cutAway("queued", false, false), false);
  assert.equal(cutAway("done", false, false), true);         // finished and not today - behind "show older"
  assert.equal(cutAway("dropped", false, false), true);
  assert.equal(cutAway("done", true, false), false);         // finished today - shown
});

test("show older lifts the cut off everything", () => {
  assert.equal(cutAway("done", false, true), false);
  assert.equal(cutAway("dropped", false, true), false);
});

// the rows that prompted it: TQ-0667 and TQ-0664, both `waiting` and both last touched 2026-09-21,
// counted for the in-progress pill and not for all.
test("all is a superset of its own buckets", () => {
  const rows = [{ key: "needs_you", today: false }, { key: "needs_you", today: false },
    { key: "needs_you", today: true }, { key: "done", today: true }, { key: "done", today: false }];
  const shown = (pred) => rows.filter((r) => !cutAway(r.key, r.today, false)).filter(pred).length;
  const all = shown(() => true), done = shown((r) => r.key === "done");
  const live = shown((r) => !["done", "dropped"].includes(r.key));
  assert.equal(live, 3);
  assert.equal(done, 1);
  assert.equal(all, live + done);
});

// Remind me compares local 'YYYY-MM-DD HH:MM:SS' strings, the shape the server writes RemindAt in.
test("localStamp writes local time in the server's RemindAt shape, zero-padded", () => {
  assert.equal(localStamp(new Date(2026, 0, 2, 3, 4, 5)), "2026-01-02 03:04:05");
  assert.equal(localStamp(new Date(2026, 11, 31, 23, 59, 59)), "2026-12-31 23:59:59");
});

test("remindWaiting is true only for an open task whose RemindAt is still ahead", () => {
  const now = "2026-09-28 12:00:00";
  const at = "2026-09-29 07:00:00";
  assert.equal(remindWaiting({ Status: "open", RemindAt: at }, now), true);
  assert.equal(remindWaiting({ Status: "working", RemindAt: at }, now), true);
  assert.equal(remindWaiting({ Status: "done", RemindAt: at }, now), false);
  assert.equal(remindWaiting({ Status: "dropped", RemindAt: at }, now), false);
  assert.equal(remindWaiting({ Status: "open" }, now), false);
  assert.equal(remindWaiting({ Status: "open", RemindAt: "" }, now), false);
  assert.equal(remindWaiting({ Status: "open", RemindAt: now }, now), false);
  assert.equal(remindWaiting({ Status: "open", RemindAt: "2026-09-28 07:00:00" }, now), false);
  assert.equal(remindWaiting(null, now), false);
});

test("remindDay is empty without a day and names the day it has", () => {
  assert.equal(remindDay(""), "");
  assert.equal(remindDay(null), "");
  const expected = new Date(2026, 9, 9).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
  assert.equal(remindDay("2026-10-09 07:00:00"), expected);
});

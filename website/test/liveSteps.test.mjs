// SHOW THE WORK AS IT HAPPENS (the owner, 2026-11-05: "it has to show what it's working on a little more than this like pulling from url's
// etc.. look how other chat libraries show intermediately the tool calls etc.") and THE TURN'S CLOCK ("it should show right when it starts the
// counter on top, then it stops when response is generated")
import assert from "node:assert/strict";

import test from "node:test";
import { describeCall, pageOf, present, stepLabel, stepsOf } from "../src/agentSteps.js";
import { clockText, turnFrom, turnStamp } from "../src/agentWork.js";


const doing = (name, args) => stepLabel({ ...describeCall(name, args), status: "running" });
const did = (name, args) => stepLabel({ ...describeCall(name, args), status: "done" });

test("a running step says what it is doing, from the call's own arguments", () => {
  assert.equal(doing("WebSearch", { query: "northwind budget policy" }), 'Searching the web for "northwind budget policy"');
  assert.equal(doing("WebFetch", { url: "https://docs.northwind.example/budget/review" }), "Reading docs.northwind.example/budget/review");
  assert.equal(doing("Bash", { command: "agent-browser open https://portal.vendor.example/login" }), "Opening portal.vendor.example in the browser");
  assert.equal(doing("Read", { file_path: "/srv/northwind/notes.md" }), "Reading notes.md");
  assert.equal(doing("Write", { file_path: "/work/outputs/report.csv" }), "Writing report.csv");
  assert.equal(doing("Bash", { command: "npm test -- --watch" }), "Running npm test -- --watch");
  assert.equal(doing("mcp__taskuary__my_task", {}), "Looking at the task's emails");
  assert.equal(doing("mcp__taskuary__search_messages", { words: "invoice" }), 'Searching your mail for "invoice"');
  // ...and once done, the same step in the past
  assert.equal(did("WebFetch", { url: "https://docs.northwind.example/budget/review" }), "Read docs.northwind.example/budget/review");
  assert.equal(did("mcp__taskuary__my_task", {}), "Looked at the task's emails");
  assert.equal(present("Edited app.py"), "Editing app.py");
  assert.equal(present("Build the report"), "Build the report", "the agent's own words stay its own");
});

test("an address is shown as host and path - never its query string, a sign-in, or a key in its path", () => {
  assert.equal(pageOf("https://user:pw@www.docs.northwind.example/budget/review?token=abc123&x=1#top"), "docs.northwind.example/budget/review");
  assert.equal(pageOf("https://api.vendor.example/v1/files/ab12cd34ef56gh78ij90kl12mn34/raw"), "api.vendor.example/v1/files/…/raw");
  for (const s of [doing("WebFetch", { url: "https://vendor.example/a?key=SECRET" }), doing("Bash", { command: "curl -s 'https://vendor.example/a?key=SECRET'" })])
    assert.ok(!/SECRET|key=|pw@/.test(s), s);
});

test("a run of calls still under way says its newest one", () => {
  const call = (id, file_path) => ({ type: "tool_call", name: "Read", detail: { tool_call_id: id, args: { file_path } } });
  const [s] = stepsOf([call("a", "/n/Budget/StatusBoard.js"), { type: "tool_result", name: "a", detail: { result: "ok" } }, call("b", "/n/Budget/BudgetTable.js")], { keepStart: false });
  assert.equal(s.status, "running");
  assert.equal(stepLabel(s), "Reading BudgetTable.js");
  assert.equal(s.summary, "Read StatusBoard.js and BudgetTable.js");
});

test("the turn's stamp: working m:ss while it runs, ran once it answered, nothing it cannot know", () => {
  const t0 = Date.parse("2026-11-05T15:00:00");
  assert.equal(turnStamp({ running: true, start: t0, now: t0 + 42_000 }), "working 0:42");
  assert.equal(turnStamp({ running: true, start: t0, now: t0 + 72_400 }), "working 1:12");
  assert.equal(turnStamp({ running: false, start: t0, end: t0 + 72_000 }), "ran 1m 12s");
  assert.equal(turnStamp({ running: true, start: null, now: t0 }), "", "no start, no counter");
  assert.equal(turnStamp({ running: false, start: t0, end: t0 + 7 * 3600_000 }), "", "a chat come back to hours later is no turn's run");
  assert.equal(clockText(3_725_000), "1:02:05");
});

// THE OWNER, 2026-11-23: a head read "ran 1m 15s" while its steps went on for five minutes - the work went on in turns drawn under that head
// (a second turn of the session, a wake, its answer filed after), and the head counted its own first part only
test("a head's clock is every turn drawn under it, each to its last step - never the first part, never the gap before a wake", async () => {
  const { folds, ranUnder } = await import("../src/chatStream.js");
  const turn = (id, state, ran) => ({ kind: "turn", id, state, ...(ran != null ? { ran } : {}) });
  const items = [{ kind: "line", id: "l1" }, turn("t1", "done", 75), turn("t2", "done", 180), turn("t3", "done", 45), { kind: "line", id: "l2" },
    turn("t4", "failed", 10), turn("t5", "done", 20), turn("t6", "working")];
  assert.deepEqual(items.map((x, i) => folds(items[i - 1], x)), [false, false, true, true, false, false, false, false]);
  assert.equal(ranUnder(items, 1), 300, "75 + 180 + 45: all of it under the one head");
  assert.equal(turnStamp({ start: 1, end: 1 + ranUnder(items, 1) * 1000 }), "ran 5m 0s");
  assert.equal(ranUnder(items, 5), 10, "a failed turn's head is its own - Try again's turn stands under it with its own");
  assert.equal(ranUnder(items, 6), 20);
});


// THE CLOCK COUNTS FROM THE PRESS AND NEVER RESTARTS (the owner, 2026-11-10; the recorded coding walk: "ran 9s" under his line while the adapter
// started, then "ran 2s" once the turn's own row came - its clock from the turn's first step): a running turn counts from the earlier of its own
// start and the line it answers - a mail that joined mid-turn is newer than the turn and never sets it back
test("a running turn's clock is the earlier of its start and the line it answers", () => {
  assert.equal(turnFrom(9000, 1000), 1000, "the adapter took 8 s: still from the press");
  assert.equal(turnFrom(1000, 5000), 1000, "a mail joined at 5 s: still from the turn's start");
  assert.equal(turnFrom(null, 1000), 1000); assert.equal(turnFrom("2026-11-10T10:00:00Z", null), Date.parse("2026-11-10T10:00:00Z"));
  assert.equal(turnFrom(null, null), null);
});

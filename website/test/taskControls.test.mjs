// Every task-view control says what it does to the task and to the agent, and runs the shared operations road
// (PW-215..PW-221). The browser harness runs in demo mode, where mutating requests are denied, so behaviour is
// proven by the backend TestClient tests (tests/test_task_controls_operations.py) and these source assertions.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");
const tasks = src("TasksView.jsx");

test("each control carries the caption that names its effect on task versus agent", () => {
  for (const [label, title] of [
    ["Mark task done", "Closes the task and ends the live agent session with it."],
    ["Reopen task", "Reopens the task only. No agent starts until you choose one."],
    ["Save result & end session", "The task stays open: Mark task done completes it and drafts the reply."],
    ["Save stopped run result", "Saves the stopped session's result and report. The task stays open."],
    ["End session & save handover", "Nothing keeps running."],
    ["Stop session", "Ends the session without a report or handover. The task keeps its state."],
    ["Write reply", "Nothing is sent until you approve it."],
    ["Generate reply", "Nothing is sent until you approve it."],
    ["Ask sender", "nothing is sent now."],
    ["Review changes", "Nothing is approved or committed here."],
  ]) {
    const at = tasks.indexOf(`>${label}</Button>`);
    assert.notEqual(at, -1, `${label} button`);
    const opening = tasks.lastIndexOf("<Button", at);
    assert.ok(tasks.slice(opening, at).includes(title), `${label}: caption "${title}"`);
  }
});

test("complete, reopen, coding start and stop run the shared operations road, never a second path", () => {
  assert.match(tasks, /runOperation\(api, "task\.complete", selected\)/);
  assert.match(tasks, /runOperation\(api, "task\.reopen", selected\)/);
  assert.match(tasks, /runOperation\(api, "dispatch\.prepare", id, \{ kind: "coding"/);
  assert.match(tasks, /runOperation\(api, "agent\.stop", id\)/);
  const start = tasks.slice(tasks.indexOf("const startCodingAgent"), tasks.indexOf("const startGeneralAgent"));
  assert.doesNotMatch(start, /Kind: "coding"/, "no Kind PATCH before a terminal");
  assert.doesNotMatch(start, /openTerm\(/, "the terminal comes from dispatch");
  assert.doesNotMatch(tasks, /patch\(\{ Status: "open" \}\)/, "reopen is an operation, not a raw PATCH");
});

test("saving a result never completes the task, drafts never send, a question waits in Review", () => {
  assert.match(tasks, /\/wrap`, \{ close: false \}/);
  assert.match(tasks, /\/reply`, \{ draft: generate \}/);
  assert.match(tasks, /\/clarify`, \{ body: text/);
  assert.doesNotMatch(tasks, /\/send`/);
});

test("the operations helper proposes then executes by version and surfaces a failed handler", () => {
  const ops = src("taskOps.js");
  assert.match(ops, /api\.post\("\/api\/operations", \{ kind, target, params \}\)/);
  assert.match(ops, /\/execute`, \{ version: op\.version \}/);
  assert.match(ops, /status === "error"\) throw/);
});

test("interrupted work shows as interrupted and reopening starts nothing", () => {
  assert.match(tasks, /includes\("interrupted"\) && <Chip/);
  const from = tasks.indexOf("const reopen =");
  const reopen = tasks.slice(from, tasks.indexOf("};", from));
  assert.doesNotMatch(reopen, /dispatch/);
});

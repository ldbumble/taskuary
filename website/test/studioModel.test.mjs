import test from "node:test";
import assert from "node:assert/strict";

import { studioAgentName, studioElapsed, studioPose, studioSeats, studioTaskState } from "../src/studioModel.js";

test("the studio seats live work first and keeps waiting work visible", () => {
  const tasks = [
    { TaskId: 1, Status: "open", Title: "queued" },
    { TaskId: 2, Status: "waiting", Title: "needs owner" },
    { TaskId: 3, Status: "in_progress", RunStatus: "running", Title: "live" },
  ];
  assert.deepEqual(studioSeats(tasks, 2).map((task) => task.TaskId), [3, 2]);
  assert.equal(studioSeats(tasks, 99).length, 8);
});

test("a real run name and task state drive the character", () => {
  const task = { Status: "in_progress", Kind: "coding", Assignee: "agent:fallback", RunStatus: "running" };
  const live = { AgentName: "codex", StartedAt: "2026-09-10 12:00:00" };
  assert.equal(studioAgentName(task, live, [{ Name: "coder" }]), "codex");
  assert.equal(studioPose(task), "type");
  assert.deepEqual(studioTaskState(task, live, [], Date.parse("2026-09-10T12:14:00")), {
    agent: "codex", label: "working · 14m", tone: "working", pose: "type",
  });
});

test("an owner wait raises the agent's hand", () => {
  const task = { Status: "waiting", Kind: "coding", Assignee: "agent:atlas" };
  assert.deepEqual(studioTaskState(task, null), {
    agent: "atlas", label: "waiting on you", tone: "waiting", pose: "hand",
  });
});

test("studioElapsed shows seconds under 90s, minutes under 90m, then hours", () => {
  const now = new Date("2026-09-28T12:00:00").getTime();
  const started = (sec) => ({ RunStartedAt: new Date(now - sec * 1000).toISOString() });
  assert.equal(studioElapsed(started(0), null, now), "0s");
  assert.equal(studioElapsed(started(89), null, now), "89s");
  assert.equal(studioElapsed(started(90), null, now), "2m");
  assert.equal(studioElapsed(started(5399), null, now), "90m");
  assert.equal(studioElapsed(started(5400), null, now), "1.5h");
  assert.equal(studioElapsed(started(-60), null, now), "0s");
  assert.equal(studioElapsed({}, null, now), "");
  assert.equal(studioElapsed(null, null, now), "");
});

test("studioElapsed takes the live row's start first, then the session's, then the run's", () => {
  const now = new Date("2026-09-28T12:00:00").getTime();
  const at = (sec) => new Date(now - sec * 1000).toISOString();
  const task = { Session: { started: at(20) }, RunStartedAt: at(30) };
  assert.equal(studioElapsed(task, { StartedAt: at(10) }, now), "10s");
  assert.equal(studioElapsed(task, {}, now), "20s");
  assert.equal(studioElapsed({ RunStartedAt: at(30) }, null, now), "30s");
  assert.equal(studioElapsed(task, { StartedAt: "2026-09-28 11:59:55" }, now), "5s");
});

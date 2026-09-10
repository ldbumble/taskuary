import test from "node:test";
import assert from "node:assert/strict";

import { studioAgentName, studioPose, studioSeats, studioTaskState } from "../src/studioModel.js";

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

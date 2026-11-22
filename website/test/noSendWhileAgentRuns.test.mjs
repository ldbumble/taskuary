// NO "SEND TO AGENT" WHILE AN AGENT RUNS (the owner, 2026-10-01): a task with a live agent session is not offered to another
// agent - its own session is the way in (Continue / the session's card). The server's dispatch door refuses it too.
import test from "node:test";
import assert from "node:assert/strict";


import { agentRuns } from "../src/taskFilter.js";


test("an item an agent is working - or a live session holds - reads as running; a stopped or saved one does not", () => {
  assert.equal(agentRuns({ kind: "message", working: "coding" }), true);
  assert.equal(agentRuns({ kind: "agent", sid: "s1", lane: "working" }), true);
  assert.equal(agentRuns({ kind: "agent", sid: "s1", lane: "stopped" }), false);
  assert.equal(agentRuns({ kind: "agent", sid: "s1", paused: true }), false);
  assert.equal(agentRuns({ kind: "message", tid: 4 }), false);
  assert.equal(agentRuns(null), false);
});

import test from "node:test";
import assert from "node:assert/strict";
import { agentPhase, ownerControlsCompletion, replyPhase, taskPhase, timelinePhases } from "../src/taskLifecycle.js";

test("task, agent and reply phases remain independent", () => {
  assert.equal(taskPhase("in_progress"), "in progress");
  assert.equal(agentPhase({ session: { alive: true, waiting: false } }), "working");
  assert.equal(replyPhase([{ Status: "pending", Kind: "draft" }]), "draft ready");
});

test("owner completion policy is carried by the durable task tag", () => {
  assert.equal(ownerControlsCompletion({ Tags: "repo:x,stay:open" }), true);
  assert.equal(ownerControlsCompletion({ TaskTags: "coding" }), false);
});

test("timeline exposes task state beside current agent or reply attention", () => {
  assert.deepEqual(timelinePhases({ TaskStatus: "waiting", AgentWaiting: true }),
    { task: "waiting", agent: "needs you", reply: null });
  assert.deepEqual(timelinePhases({ TaskStatus: "done", ReviewStatus: "sent" }),
    { task: "done", agent: null, reply: "sent" });
});

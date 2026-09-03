import test from "node:test";
import assert from "node:assert/strict";
import {
  agentPhase, ownerControlsCompletion, pendingReplyReview, replyPhase, sentReplyReview, taskPhase, timelinePhases,
} from "../src/taskLifecycle.js";

test("task, agent and reply phases remain independent", () => {
  assert.equal(taskPhase("in_progress"), "in progress");
  assert.equal(agentPhase({ session: { alive: true, waiting: false } }), "working");
  assert.equal(replyPhase([{ Status: "pending", Kind: "draft" }]), "draft ready");
});

test("an action proposed after a reply never replaces the sender's draft", () => {
  const action = { ReviewId: 12, Status: "pending", Kind: "action", DraftText: '{"action":"write_playbook"}' };
  const reply = { ReviewId: 11, Status: "pending", Kind: "draft_reply", DraftText: "Answers to all eight items." };
  const reviews = [action, reply];
  assert.equal(pendingReplyReview(reviews), reply);
  assert.equal(replyPhase(reviews), "draft ready");
  assert.equal(replyPhase([action]), "not drafted");
});

test("an approved action is not mistaken for a sent reply", () => {
  const action = { ReviewId: 12, Status: "approved", Kind: "action" };
  const reply = { ReviewId: 11, Status: "sent", Kind: "draft_reply", DraftText: "Sent answer." };
  assert.equal(sentReplyReview([action, reply]), reply);
  assert.equal(replyPhase([action]), "not drafted");
  assert.equal(replyPhase([action, reply]), "sent");
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

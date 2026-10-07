// A task says what closes it (spec 2026-10-05): its emails are slot reviews, shown in their own block - never the reply card.
import test from "node:test";
import assert from "node:assert/strict";
import { pendingReplyReview, sentReplyReview, slotReviews, unsentReplyReview } from "../src/taskLifecycle.js";

const slot = { ReviewId: 9, Kind: "slot", Status: "pending", DraftText: "Tab 1 is fine." };
const reply = { ReviewId: 3, Kind: "draft_reply", Status: "pending", DraftText: "Thanks, done." };

test("a slot draft is never the task's reply", () => {
  assert.equal(pendingReplyReview([slot]), undefined);
  assert.equal(pendingReplyReview([slot, reply]), reply);
  assert.equal(sentReplyReview([{ ...slot, Status: "approved" }]), undefined);
  assert.equal(unsentReplyReview([{ ...slot, Status: "rejected" }]), undefined);
});

test("the slot block gets every slot review", () => {
  assert.deepEqual(slotReviews([reply, slot, { ...slot, ReviewId: 10 }]).map((r) => r.ReviewId), [9, 10]);
});

test("each email says where it stands", async () => {
  const { slotState } = await import("../src/taskLifecycle.js");
  assert.equal(slotState({ done: false }, undefined), "to draft");
  assert.equal(slotState({ done: false }, slot), "waits for your yes");
  assert.equal(slotState({ done: true }, { ...slot, Status: "approved" }), "sent");
  assert.equal(slotState({ done: true }, { ...slot, Status: "rejected" }), "dropped");
  assert.equal(slotState({ done: true }, undefined), "dropped");
});

test("Approve all never sweeps up an email the agent added, or one with no address", async () => {
  const { bulkSendable } = await import("../src/taskLifecycle.js");
  const items = [{ rid: 9, out: { to: "a@x.example" } }, { rid: 10, out: { to: "b@x.example", by: "agent" } }, { rid: 11, out: { to: "Gail" } }];
  const reviews = [slot, { ...slot, ReviewId: 10 }, { ...slot, ReviewId: 11 }];
  assert.deepEqual(bulkSendable(items, reviews).map((r) => r.ReviewId), [9]);
});

test("the footer says what closes the task", async () => {
  const { completionLine } = await import("../src/taskLifecycle.js");
  assert.match(completionLine(true, false), /sending the reply closes it/);
  assert.match(completionLine(true, true), /closes when its emails are sent or dropped/);
  assert.match(completionLine(false, false), /Automatic task/);
  assert.match(completionLine(true, false, true), /press Mark done/);       // nobody to answer: no reply to send
});

test("waiting emails open Close out, and it says how many", async () => {
  const { focusStage, waitingEmails } = await import("../src/taskLifecycle.js");
  const checklist = [{ id: "a", out: { to: "p@x.example" }, rid: 9 }, { id: "b", out: { to: "Gail" } }];
  assert.equal(waitingEmails(checklist, [slot]), 1);
  assert.equal(focusStage({ kind: "coding", task: "waiting", agent: "session saved", emails: 1 }), "reply");
  assert.equal(focusStage({ kind: "coding", task: "waiting", agent: "agent waiting on you", emails: 1 }), "agent");
});

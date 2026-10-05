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

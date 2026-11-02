import test from "node:test";
import assert from "node:assert/strict";
import { draftAnswers, otherPendingReplies } from "../src/pendingDrafts.js";

// TWO LETTERS WAITING ON ONE TASK (2026-11-02): an agent's question to one person and a reply to another - each drawn with what it answers.
// Invented people.
const msgs = [
  { MessageId: 1, FromName: "Gail Moreno", FromEmail: "gail@northwind.example", BodyText: "Can you update the budget inputs?" },
  { MessageId: 2, FromName: "Paula Vance", FromEmail: "paula@northwind.example", BodyText: "Perfect!" },
];
const toGail = { ReviewId: 10, MessageId: 1, Kind: "draft_reply", Status: "pending", DraftText: "Which rate should I use?" };
const toPaula = { ReviewId: 12, MessageId: 2, Kind: "draft_reply", Status: "pending", DraftText: "Glad it helped." };

test("each pending reply answers its own message, not the task's newest", () => {
  assert.equal(draftAnswers(toGail, msgs).FromName, "Gail Moreno");
  assert.equal(draftAnswers(toPaula, msgs).FromName, "Paula Vance");
  assert.equal(draftAnswers({ ReviewId: 1, MessageId: 99 }, msgs), null);
  assert.equal(draftAnswers(null, msgs), null);
});

test("the other pending replies are drawn beside the one Close out shows - never a sent one, a slot or a proposal", () => {
  const reviews = [toPaula, toGail, { ReviewId: 9, MessageId: 1, Kind: "draft_reply", Status: "approved" },
    { ReviewId: 11, Kind: "slot", Status: "pending" }, { ReviewId: 13, Kind: "action", Status: "pending" }];
  assert.deepEqual(otherPendingReplies(reviews, toPaula).map((r) => r.ReviewId), [10]);
  assert.deepEqual(otherPendingReplies(reviews, null).map((r) => r.ReviewId), [10, 12]);
  assert.deepEqual(otherPendingReplies([toGail], toGail), []);
});

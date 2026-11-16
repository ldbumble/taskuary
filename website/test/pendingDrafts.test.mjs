import test from "node:test";
import assert from "node:assert/strict";
import { draftAnswers } from "../src/pendingDrafts.js";

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

test("a reply answers the mail that asked (AnswersMid), not the newest it saw (MessageId)", () => {
  assert.equal(draftAnswers({ AnswersMid: 11, MessageId: 13 }, [{ MessageId: 11 }, { MessageId: 13 }]).MessageId, 11);
  assert.equal(draftAnswers({ AnswersMid: null, MessageId: 13 }, [{ MessageId: 11 }, { MessageId: 13 }]).MessageId, 13);
});

// A reply closed without sending stays on its task - done or not (the owner, 2026-09-24: "draft should
// always stay on task even on done task"). The data always kept it; the page only ever looked for a
// pending or a sent one, so a closed task's draft was there and never shown.
import test from "node:test";
import assert from "node:assert/strict";

import { chatReplyShown } from "../src/agentSummary.js";
import { isUnsentReply, unsentReplyReview } from "../src/taskLifecycle.js";

test("the newest reply closed without sending is the one the task keeps", () => {
  const rows = [
    { ReviewId: 1, Kind: "draft", Status: "no_reply", DraftText: "older words" },
    { ReviewId: 3, Kind: "draft_reply", Status: "closed_unsent", DraftText: "the agent's reply" },
    { ReviewId: 2, Kind: "draft", Status: "rejected", DraftText: "middle" },
  ];
  assert.equal(unsentReplyReview(rows).ReviewId, 3);
});

test("a sent reply, an action, or a draft with no words is not an unsent reply", () => {
  assert.equal(unsentReplyReview([{ ReviewId: 1, Kind: "draft", Status: "sent", DraftText: "x" }]), undefined);
  assert.equal(unsentReplyReview([{ ReviewId: 1, Kind: "action", Status: "no_reply", DraftText: "x" }]), undefined);
  assert.equal(unsentReplyReview([{ ReviewId: 1, Kind: "draft", Status: "no_reply", DraftText: "  " }]), undefined);
  assert.equal(unsentReplyReview(), undefined);
});

// Walk 6: a chat reply to Paula Vance closed without sending - its words had gone to her as an email - stood as the LAST thing in the chat,
// drawn by a second block after the stream with a live "Bring it back to send". One road now: each reply that did not go is greyed in the
// turn that wrote it (isUnsentReply, the stream's test), and the foot draws no reply place for it at all.
test("a reply that did not go is the stream's greyed card, never a reply place at the chat's foot", () => {
  const replyMessage = { MessageId: 7, FromName: "Paula Vance", Channel: "teams" };
  const gone = { ReviewId: 12, Kind: "draft_reply", Status: "closed_unsent", DraftText: "Gail asked for 40 copies - printing them today." };
  assert.equal(isUnsentReply(gone), true);
  assert.equal(chatReplyShown({ replyMessage, unsentReview: gone }), false);
  for (const r of [{ ...gone, Status: "pending" }, { ...gone, Status: "sent" }, { ...gone, Kind: "action" }, { ...gone, DraftText: " " }])
    assert.equal(isUnsentReply(r), false, JSON.stringify(r));
});

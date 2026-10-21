import test from "node:test";
import assert from "node:assert/strict";
import { rowMeta } from "../src/funnelPile.js";
import { NOT_SENT, READY, focusStage, replyPhase } from "../src/taskLifecycle.js";

// A SEND THE MAIL SERVER REFUSED read "ready to send" in green on the rail and the card (the UI audit, 2026-10-21)
test("a refused send's rail row says not sent, in the failure colour", () => {
  const ok = rowMeta({ lane: "approve", kind: "review" }), refused = rowMeta({ lane: "approve", kind: "review", not_sent: true });
  assert.equal(ok.word, READY);
  assert.equal(refused.word, "didn't send"); assert.equal(refused.role, "bad");
});

test("a refused send's reply phase is not sent, and the reply still opens first", () => {
  const draft = { Kind: "reply", Status: "pending", DraftText: "Signed this morning." };
  assert.equal(replyPhase([draft]), READY);
  assert.equal(replyPhase([{ ...draft, DeliveryState: "failed" }]), NOT_SENT);
  assert.equal(NOT_SENT, "didn't send");
  assert.equal(focusStage({ kind: "reply", reply: NOT_SENT, hasSender: true }), "reply");
});

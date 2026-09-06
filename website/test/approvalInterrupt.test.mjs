// The approval interruption (PW-239): built from the decide answer, never from a guess; cancel keeps
// the owner's edit and sends nothing; "review the update" hands the refreshed draft over for a fresh yes.
import test from "node:test";
import assert from "node:assert/strict";
import { interruptOf, resolveInterrupt, captureInterruptedReply, interruptedReplyTarget, restoreInterruptedReply } from "../src/approvalInterrupt.js";

const stale = {
  ok: false, stale: true, send_error: "New messages arrived after this draft.",
  interrupt: { title: "A new message arrived. Review it before sending.",
    latest: { MessageId: 7, FromName: "Dana", SentAt: "2026-09-06 10:30:00", preview: "Actually - September too, please." },
    triage: "Triage: the ask now covers September as well.", yours: "Here it is - my edited version.", refreshed: "Both months are attached." },
};

test("a stale answer becomes an interruption the owner can act on", () => {
  const it = interruptOf(stale, 3);
  assert.equal(it.reviewId, 3);
  assert.equal(it.title, "A new message arrived. Review it before sending.");
  assert.equal(it.latest.preview, "Actually - September too, please.");
  assert.equal(it.triage, "Triage: the ask now covers September as well.");
  assert.equal(it.yours, "Here it is - my edited version.");
  assert.equal(it.refreshed, "Both months are attached.");
  assert.deepEqual(it.actions, ["review", "cancel"]);
});

test("a sent reply, a plain send failure and a decided review are not interruptions", () => {
  assert.equal(interruptOf({ ok: true, status: "approved" }, 3), null);
  assert.equal(interruptOf({ ok: true, send_error: "graph sendMail failed (403)" }, 3), null);
  assert.equal(interruptOf({ ok: false, already: true }, 3), null);
});

test("an older stale answer without the payload still interrupts, with what it has", () => {
  const it = interruptOf({ ok: false, stale: true, draft: "refreshed words", send_error: "New messages arrived after this draft." }, 3);
  assert.equal(it.title, "A new message arrived. Review it before sending.");
  assert.equal(it.refreshed, "refreshed words");
  assert.equal(it.latest, null);
});

test("cancel keeps the owner's edit in the box and sends nothing; review hands over the refreshed draft beside it", () => {
  const it = interruptOf(stale, 3);
  const edits = { 3: "Here it is - my edited version." };
  const cancelled = resolveInterrupt(it, "cancel", edits);
  assert.deepEqual(cancelled, { edits: { 3: "Here it is - my edited version." }, compare: null, send: false });
  const reviewed = resolveInterrupt(it, "review", edits);
  assert.equal(reviewed.send, false);
  assert.equal(reviewed.edits[3], "Here it is - my edited version.");          // the owner's words stay where they typed them
  assert.deepEqual(reviewed.compare, { reviewId: 3, yours: "Here it is - my edited version.", refreshed: "Both months are attached." });
});

test("All retains the exact attempted edit after its original member loses the review", () => {
  const original = { ProcessingItemId: "pi-one", MessageId: 2, OpenTarget: { kind: "message", id: 2 } };
  const saved = captureInterruptedReply(interruptOf(stale, 3), original, "  /Data >= 7\nowner wording  ");
  original.MessageId = 99;
  assert.equal(saved.row.MessageId, 2);
  assert.equal(saved.yours, "  /Data >= 7\nowner wording  ");
  assert.equal(resolveInterrupt(saved, "cancel", {}).send, false);
  assert.equal(saved.yours, "  /Data >= 7\nowner wording  ");
  const target = interruptedReplyTarget(saved, [{ ProcessingItemId: "pi-two", MessageId: 8,
    ProcessingMemberIds: ["message:7", "message:8"], OpenTarget: { kind: "message", id: 8 } }]);
  assert.equal(target.ProcessingItemId, "pi-two");
  assert.equal(target.MessageId, 7);
  assert.deepEqual(target.OpenTarget, { kind: "message", id: 7 });
});

test("All restores only the exact pending review after authoritative detail hydration", () => {
  const saved = captureInterruptedReply(interruptOf(stale, 3), { MessageId: 2 }, "owner edit");
  const row = { ProcessingItemId: "pi-one", MessageId: 7 };
  const chosen = { ReviewId: 3, MessageId: 7, Kind: "draft", Status: "pending", DraftText: "newest persisted draft" };
  const detail = { reviews: [{ ...chosen, ReviewId: 4, DraftText: "another pending reply" }, chosen] };
  const restored = restoreInterruptedReply(saved, { row, detail });
  assert.equal(restored.owner, "pi-one|review:3");
  assert.equal(restored.yours, "owner edit");
  assert.equal(restored.compare.refreshed, "newest persisted draft");
  assert.deepEqual(restored.detail.reviews, [chosen]);
  assert.equal(detail.reviews.length, 2);
  for (const wrong of [{ ...chosen, MessageId: 2 }, { ...chosen, ReviewId: 4 }, { ...chosen, Status: "sent" }]) {
    assert.throws(() => restoreInterruptedReply(saved, { row, detail: { reviews: [wrong] } }), /Your edit is saved/);
  }
  assert.throws(() => restoreInterruptedReply(saved, { row: { ...row, MessageId: 2 }, detail }), /Your edit is saved/);
});

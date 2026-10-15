import assert from "node:assert/strict";
import test from "node:test";

import {
  fullProcessingRow,
  isCoveragePending,
  processingDetailPath,
  processingMessageDetail,
  processingRefreshCandidate,
  processingSelectionKey,
  processingTransportLimit,
  rowOwnsMessage,
  unreadProcessingRows,
} from "../src/processingAll.js";

// the canonical envelope a Work row carries (unreadProcessingRows builds it from the pile)
const row = (id, target = { kind: "message", id: 7 }, members = [`${target.kind}:${target.id}`], extra = {}) => ({
  ProcessingItemId: id, ProcessingMemberIds: members, ViewRevision: `view-${id}`, OpenTarget: target,
  MessageId: target.kind === "message" ? target.id : null, ...extra,
});

test("a refresh never asks the transport for more than its 500-row bound", () => {
  assert.equal(processingTransportLimit(607), 500);
  assert.equal(processingTransportLimit(107), 107);
  assert.equal(processingTransportLimit(0), 1);
});

test("canonical Work reuses its pile envelope instead of fetching it again", () => {
  const rows = unreadProcessingRows({ canonical: true, rev: "pile-rev", items: [{
    key: "processing:root-a", processing_id: "root-a",
    member_ids: ["message:7", "task:2"], context_revision: "context-a", view_revision: "view-a",
    mid: 7, tid: 2, when: "2026-09-06 09:30:00", title: "Unread title", who: "Dana",
    preview: "Unread preview", channel: "email", source: "owner@example.test",
    category: "info", status: "filed", unread: true,
  }] });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].ProcessingItemId, "root-a");
  assert.deepEqual(rows[0].ProcessingMemberIds, ["message:7", "task:2"]);
  assert.deepEqual(rows[0].OpenTarget, { kind: "message", id: 7 });
  assert.equal(rows[0].SentAt, "2026-09-06 09:30:00");
  assert.equal(rows[0].Unread, 1);
  assert.equal(unreadProcessingRows({ canonical: false, items: [] }), null);
});

// The lane is the row's own word and the pile already decided it. Dropping it here left the work rail
// showing triage's road chip and a 9px state glyph, so an agent that had stopped and put its hand up
// read "chat" with a hand too small to find (the owner, 2026-09-11: "it should show agent waving").
test("an unread row keeps the pile's lane, so a waving agent wears its own word", () => {
  const pile = (lane, kind) => unreadProcessingRows({ canonical: true, rev: "pile-rev", items: [{
    key: `processing:root-${lane}`, processing_id: `root-${lane}`, member_ids: ["task:507"],
    context_revision: "c", view_revision: "v", tid: 507, kind, lane, title: "Install devin",
  }] })[0];
  const waving = pile("blocked", "agent");
  assert.equal(waving.Lane, "blocked");
  assert.equal(waving.AgentWaiting, 1);
  const fyi = pile("fyi", "fyi");
  assert.equal(fyi.Lane, "fyi");
  assert.equal(fyi.AgentWaiting, 0);
});

test("a coverage refusal is told apart from an ordinary failure", () => {
  const failure = (code) => ({ response: { data: { detail: { code } } } });
  assert.equal(isCoveragePending(failure("processing_coverage_pending")), true);
  assert.equal(isCoveragePending(failure("processing_snapshot_expired")), false);
  assert.equal(isCoveragePending(new Error("offline")), false);
});

test("detail identity binds root, exact member target, and view revision", () => {
  const r = row("root:a", { kind: "message", id: 7 }, ["message:7", "message:8", "task:2"]);
  assert.equal(rowOwnsMessage(r, 8), true);
  assert.equal(rowOwnsMessage(r, 9), false);
  assert.equal(processingSelectionKey(r), "root:a|message:7|view-root:a");
  assert.equal(processingSelectionKey(r, { kind: "message", id: 8 }), "root:a|message:8|view-root:a");
  assert.equal(processingDetailPath(r, { kind: "message", id: 8 }),
    "/api/processing/items/root%3Aa/detail?kind=message&id=8&view_revision=view-root%3Aa");
});

test("a refreshed rail revalidates an exact canonical selection even when its root leaves the loaded span", () => {
  const selected = row("root:a", { kind: "message", id: 7 }, ["message:7", "task:2"]);
  const fresh = row("root:a", { kind: "message", id: 8 });
  assert.equal(processingRefreshCandidate(selected, [fresh]), fresh);
  assert.equal(processingRefreshCandidate(selected, []), selected,
    "the exact selected target must be revalidated instead of disappearing with the compact row");
  assert.equal(processingRefreshCandidate({ MessageId: 7 }, []), null);
});

test("full message detail replaces removed source fields while retaining canonical envelope", () => {
  const compact = row("root-message", { kind: "message", id: 4 }, ["message:4"], { DraftError: "old error", Preview: "old preview" });
  const full = fullProcessingRow(compact, {
    item_id: "root-message",
    context_revision: "new-context",
    view_revision: "new-view",
    open_target: { kind: "message", id: 4 },
    row: { MessageId: 4, Subject: "Fresh message" },
    detail: { title: "Fresh message", body: "Full text" },
  });
  assert.equal(Object.hasOwn(full, "DraftError"), false, "removed source properties must not survive replacement");
  assert.equal(full.Subject, "Fresh message");
  assert.equal(full.Preview, "", "removed message properties must clear instead of falling back to stale compact data");
  assert.equal(full.ViewRevision, "new-view");
  assert.throws(() => fullProcessingRow(compact, {
    item_id: "another-root", open_target: { kind: "message", id: 4 }, row: {}, detail: {},
  }), /item_id mismatch/);
});

test("an exact message target cannot expose another member's pending reply", () => {
  const r = { OpenTarget: { kind: "message", id: 22 }, MessageId: 22 };
  const detail = processingMessageDetail(r, { reviews: [
    { ReviewId: 1, MessageId: 21, Status: "pending", Kind: "reply", DraftText: "wrong member" },
    { ReviewId: 2, MessageId: 22, Status: "pending", Kind: "reply", DraftText: "right member" },
    { ReviewId: 3, MessageId: null, Status: "pending", Kind: "action", DraftText: "task action" },
  ] });
  assert.deepEqual(detail.reviews.map((review) => review.ReviewId), [2, 3]);
});

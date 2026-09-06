import assert from "node:assert/strict";
import test from "node:test";

import {
  appendProcessingPage,
  compactProcessingRow,
  firstProcessingPage,
  fullProcessingRow,
  isCoveragePending,
  isSnapshotExpired,
  processingAllParams,
  processingDetailPath,
  processingMessageDetail,
  processingRefreshCandidate,
  processingSelectionKey,
  processingTransportLimit,
  rowOwnsMessage,
} from "../src/processingAll.js";

const item = (id, target = { kind: "message", id: 7 }, extra = {}) => ({
  item_id: id,
  member_ids: [`${target.kind}:${target.id}`],
  context_revision: `context-${id}`,
  view_revision: `view-${id}`,
  activity_at: "2026-09-06 09:30:00",
  activity_basis: "stored_local_wall_clock",
  title: `Title ${id}`,
  actor: "Dana",
  preview: "Compact preview",
  channel: target.kind === "message" ? "email" : "own",
  source: "dana@example.test",
  category: "info",
  status: "filed",
  counts: { members: 1, messages: target.kind === "message" ? 1 : 0, tasks: target.kind === "task" ? 1 : 0,
    ideas: target.kind === "idea" ? 1 : 0, reviews: target.kind === "review" ? 1 : 0, attachments: 2 },
  open_target: target,
  row: {},
  ...extra,
});

const page = (revision, items, next = null) => ({
  schema_version: "taskuary.processing.all.v1",
  snapshot_revision: revision,
  next_cursor: next,
  counts: { total: 507, returned: items.length },
  coverage: { complete: true },
  items,
});

test("canonical query preserves category, exact source, and opaque cursor scope", () => {
  assert.deepEqual(processingAllParams({ category: "messages", discovered: ["caldav"], limit: 37 }), {
    limit: 37, channel: "teams,slack,telegram,whatsapp,imessage,discord",
  });
  assert.deepEqual(processingAllParams({ pick: "src:email:owner:archive@example.test", cursor: "opaque==" }), {
    limit: 100, channel: "email", source: "owner:archive@example.test", cursor: "opaque==",
  });
  assert.deepEqual(processingAllParams({ pick: "channel:report" }), { limit: 100, channel: "report" });
  assert.throws(() => processingAllParams({ limit: 0 }), /between 1 and 500/);
  assert.throws(() => processingAllParams({ limit: 501 }), /between 1 and 500/);
  assert.equal(processingTransportLimit(607), 500);
  assert.equal(processingTransportLimit(607 - 500), 107);
});

test("one compact row retains canonical identity and adapts each truthful target", () => {
  for (const kind of ["message", "task", "idea", "review"]) {
    const row = compactProcessingRow(item(`root-${kind}`, { kind, id: 9 }));
    assert.equal(row.ProcessingItemId, `root-${kind}`);
    assert.deepEqual(row.OpenTarget, { kind, id: 9 });
    assert.equal(row.Subject, `Title root-${kind}`);
    assert.equal(row.SentAt, "2026-09-06 09:30:00");
    assert.equal(row.Attachments, 2);
    assert.equal(row[`${kind[0].toUpperCase()}${kind.slice(1)}Id`], 9);
  }
});

test("frozen pages concatenate once and reject mixed leases or duplicate roots", () => {
  const first = firstProcessingPage(page("lease-a", [item("a"), item("b")], "cursor-2"));
  assert.ok(first.rows.every((row) => row.AllSnapshotRevision === "lease-a"));
  const joined = appendProcessingPage(first, page("lease-a", [item("c")], null));
  assert.deepEqual(joined.rows.map((row) => row.ProcessingItemId), ["a", "b", "c"]);
  assert.equal(joined.nextCursor, null);
  assert.throws(() => appendProcessingPage(first, page("lease-b", [item("c")])), /snapshot changed/);
  assert.throws(() => appendProcessingPage(first, page("lease-a", [item("b")])), /duplicate item_id/);
  assert.throws(() => firstProcessingPage(page("lease-a", [item("a"), item("a")])), /duplicate item_id/);
});

test("coverage fallback and lease expiry are distinct from ordinary failures", () => {
  const failure = (code) => ({ response: { data: { detail: { code } } } });
  assert.equal(isCoveragePending(failure("processing_coverage_pending")), true);
  assert.equal(isSnapshotExpired(failure("processing_snapshot_expired")), true);
  assert.equal(isCoveragePending(failure("processing_snapshot_expired")), false);
  assert.equal(isCoveragePending(new Error("offline")), false);
});

test("detail identity binds root, exact member target, and view revision", () => {
  const row = compactProcessingRow(item("root:a", { kind: "message", id: 7 }, {
    member_ids: ["message:7", "message:8", "task:2"],
  }));
  assert.equal(rowOwnsMessage(row, 8), true);
  assert.equal(rowOwnsMessage(row, 9), false);
  assert.equal(processingSelectionKey(row), "root:a|message:7|view-root:a");
  assert.equal(processingSelectionKey(row, { kind: "message", id: 8 }), "root:a|message:8|view-root:a");
  assert.equal(processingDetailPath(row, { kind: "message", id: 8 }),
    "/api/processing/items/root%3Aa/detail?kind=message&id=8&view_revision=view-root%3Aa");
});

test("a refreshed rail revalidates an exact canonical selection even when its root leaves the loaded span", () => {
  const selected = compactProcessingRow(item("root:a", { kind: "message", id: 7 }, {
    member_ids: ["message:7", "task:2"],
  }));
  const fresh = compactProcessingRow(item("root:a", { kind: "message", id: 8 }));
  assert.equal(processingRefreshCandidate(selected, [fresh]), fresh);
  assert.equal(processingRefreshCandidate(selected, []), selected,
    "the exact selected target must be revalidated instead of disappearing with the compact row");
  assert.equal(processingRefreshCandidate({ MessageId: 7 }, []), null);
});

test("full message detail replaces removed source fields while retaining canonical envelope", () => {
  const compact = compactProcessingRow(item("root-message", { kind: "message", id: 4 }, {
    row: { DraftError: "old error", Preview: "old preview" },
  }));
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
  const row = { OpenTarget: { kind: "message", id: 22 }, MessageId: 22 };
  const detail = processingMessageDetail(row, { reviews: [
    { ReviewId: 1, MessageId: 21, Status: "pending", Kind: "reply", DraftText: "wrong member" },
    { ReviewId: 2, MessageId: 22, Status: "pending", Kind: "reply", DraftText: "right member" },
    { ReviewId: 3, MessageId: null, Status: "pending", Kind: "action", DraftText: "task action" },
  ] });
  assert.deepEqual(detail.reviews.map((review) => review.ReviewId), [2, 3]);
});

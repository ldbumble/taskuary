export const PROCESSING_ALL_MAX_PAGE = 500;

const object = (value) => value && typeof value === "object" && !Array.isArray(value);
const text = (value) => value == null ? "" : String(value);

export const processingTransportLimit = (wanted) => Math.min(PROCESSING_ALL_MAX_PAGE, Math.max(1, Math.trunc(wanted)));

// `error.detail` FIRST: api.js keeps the structured body there and leaves a string in
// response.data.detail for display. Read the display copy first and every code below is a JSON
// blob that matches nothing - which is how "membership is being reconciled" became a red banner.
const detailOf = (error) => error?.detail ?? error?.response?.data?.detail;   // an HTTP error, or a streamed error event

export function processingErrorCode(error) {
  const detail = detailOf(error);
  return typeof detail === "string" ? detail : detail?.code || error?.code || "";
}

export function processingErrorMessage(error, fallback) {
  const detail = detailOf(error);
  return (typeof detail === "string" ? detail : detail?.message) || error?.message || fallback;
}

export const isCoveragePending = (error) => processingErrorCode(error) === "processing_coverage_pending";

function targetOf(item) {
  const target = item?.open_target;
  if (!object(target) || !["message", "task", "idea", "review"].includes(target.kind)
      || (typeof target.id !== "number" && typeof target.id !== "string")) {
    throw new TypeError("canonical All item has no supported open_target");
  }
  return { kind: target.kind, id: target.id };
}

// Work arrives as the canonical pile. FeedView needs a small row envelope only for its count
// header and for exact-message deep links when "Task" mode is selected.
export function unreadProcessingRows(pile) {
  if (!object(pile) || pile.canonical !== true || !Array.isArray(pile.items)) return null;
  return pile.items.flatMap((item) => {
    if (!object(item) || typeof item.processing_id !== "string" || !item.processing_id
        || !Array.isArray(item.member_ids)) return [];
    const target = item.mid != null ? { kind: "message", id: item.mid }
      : item.idea != null ? { kind: "idea", id: item.idea }
        : item.rid != null ? { kind: "review", id: item.rid }
          : item.tid != null ? { kind: "task", id: item.tid } : null;
    if (!target) return [];
    return [{
      ProcessingItemId: item.processing_id,
      ProcessingMemberIds: [...item.member_ids],
      ContextRevision: text(item.context_revision),
      ViewRevision: text(item.view_revision),
      AllSnapshotRevision: text(pile.rev),
      OpenTarget: target,
      MessageId: item.mid ?? null,
      TaskId: item.tid ?? null,
      ReviewId: item.rid ?? null,
      IdeaId: item.idea ?? null,
      SentAt: item.when || item.since || "",
      Subject: item.title || "",
      FromName: item.who || "",
      Preview: item.preview || item.summary || "",
      Channel: item.channel || "",
      SourceName: item.source || "",
      Category: item.category || "",
      MsgStatus: item.status || "",
      ProcessingCounts: { members: item.member_ids.length },
      // THE LANE IS THE ROW'S WORD, and the pile already decided it. Dropping it here made the work
      // rail fall back to triage's road chip plus a 9px state glyph, so an agent that had stopped and
      // put its hand up wore "chat" and a hand too small to find (the owner, 2026-09-11: "the little
      // waving hand is really small still... it should show agent waving"). LaneTag draws `blocked`
      // loud, with the word, which is the whole point of the lane having one.
      Lane: item.lane || "",
      AgentWaiting: item.lane === "blocked" ? 1 : 0,     // `blocked` IS the agent waiting on you
      AgentLine: item.lane === "blocked" ? item.why || "" : "",   // ...and the ONE sentence for its state (laneSays)
      Unread: item.unread ? 1 : 0,
    }];
  });
}

export const processingRowId = (row) => row?.ProcessingItemId || (row?.MessageId != null ? `legacy-message:${row.MessageId}` : "");

export function processingRefreshCandidate(selected, rows) {
  if (!selected?.ProcessingItemId) return null;
  return (rows || []).find((row) => row?.ProcessingItemId === selected.ProcessingItemId) || selected;
}

export function processingTarget(row, override = null) {
  const target = override || row?.OpenTarget;
  if (!target || !["message", "task", "idea", "review"].includes(target.kind)
      || (typeof target.id !== "number" && typeof target.id !== "string")) return null;
  return { kind: target.kind, id: target.id };
}

export function processingSelectionKey(row, override = null) {
  const target = processingTarget(row, override);
  if (!row?.ProcessingItemId || !target) return row?.MessageId != null ? `legacy-message:${row.MessageId}` : "";
  return `${row.ProcessingItemId}|${target.kind}:${target.id}|${row.ViewRevision || ""}`;
}

export function processingDetailPath(row, override = null) {
  const target = processingTarget(row, override);
  if (!row?.ProcessingItemId || !target) return null;
  const q = new URLSearchParams({ kind: target.kind, id: String(target.id) });
  if (row.ViewRevision) q.set("view_revision", row.ViewRevision);
  return `/api/processing/items/${encodeURIComponent(row.ProcessingItemId)}/detail?${q}`;
}

export function rowOwnsMessage(row, messageId) {
  return !!row?.ProcessingItemId && row.ProcessingMemberIds?.includes(`message:${messageId}`);
}

export function fullProcessingRow(compact, payload) {
  if (!object(payload) || payload.item_id !== compact?.ProcessingItemId) {
    throw new TypeError("canonical All detail item_id mismatch");
  }
  const target = targetOf(payload);
  const requested = processingTarget(compact);
  if (requested && (requested.kind !== target.kind || String(requested.id) !== String(target.id))) {
    throw new TypeError("canonical All detail open_target mismatch");
  }
  const full = object(payload.row) ? payload.row : {};
  const fallback = target.kind === "message" ? {} : compact;
  return {
    ...full,
    ProcessingItemId: compact.ProcessingItemId,
    ProcessingMemberIds: [...(compact.ProcessingMemberIds || [])],
    ContextRevision: text(payload.context_revision),
    ViewRevision: text(payload.view_revision),
    ActivityBasis: compact.ActivityBasis || "",
    OpenTarget: target,
    ProcessingCounts: { ...(compact.ProcessingCounts || {}) },
    AllSnapshotRevision: compact.AllSnapshotRevision || "",
    SentAt: full.SentAt || fallback.SentAt || "",
    Subject: full.Subject || payload.detail?.title || fallback.Subject || "",
    FromName: full.FromName || fallback.FromName || "",
    Preview: full.Preview || fallback.Preview || "",
    Channel: full.Channel || fallback.Channel || "",
    SourceName: full.SourceName || fallback.SourceName || "",
    Category: full.Category || fallback.Category || "",
    MessageId: full.MessageId ?? (target.kind === "message" ? target.id : null),
    TaskId: full.TaskId ?? (target.kind === "task" ? target.id : null),
    TaskStatus: full.TaskStatus ?? (target.kind === "task" ? (payload.detail?.status || compact.TaskStatus || "") : null),
    ReviewId: full.ReviewId ?? (target.kind === "review" ? target.id : null),
    IdeaId: full.IdeaId ?? (target.kind === "idea" ? target.id : null),
  };
}

export function processingMessageDetail(row, detail) {
  if (row?.OpenTarget?.kind !== "message" || !object(detail)) return detail || {};
  const mid = String(row.MessageId ?? row.OpenTarget.id);
  return {
    ...detail,
    // A task may contain multiple incoming messages and multiple reply reviews. Opening exact
    // member M2 must never expose or send M1's draft. Task-level action proposals remain useful.
    reviews: (detail.reviews || []).filter((review) => review?.Kind === "action"
      || (review?.MessageId != null && String(review.MessageId) === mid)),
  };
}

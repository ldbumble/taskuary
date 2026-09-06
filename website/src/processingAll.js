import { channelsForCategory } from "./feedFilters.js";

export const PROCESSING_ALL_SCHEMA = "taskuary.processing.all.v1";
export const PROCESSING_ALL_MAX_PAGE = 500;

const object = (value) => value && typeof value === "object" && !Array.isArray(value);
const text = (value) => value == null ? "" : String(value);

export function processingAllParams({ category = "", pick = "", discovered = [], limit = 100, cursor = null } = {}) {
  if (!Number.isInteger(limit) || limit < 1 || limit > PROCESSING_ALL_MAX_PAGE) {
    throw new TypeError("limit must be an integer between 1 and 500");
  }
  const params = { limit };
  if (pick.startsWith("src:")) {
    const [, channel, ...source] = pick.split(":");
    params.channel = channel;
    params.source = source.join(":");
  } else if (pick.startsWith("channel:")) {
    params.channel = pick.slice(8);
  } else {
    const channels = channelsForCategory(category, discovered);
    if (channels) params.channel = channels.join(",");
  }
  if (cursor) params.cursor = cursor;
  return params;
}

export const processingTransportLimit = (wanted) => Math.min(PROCESSING_ALL_MAX_PAGE, Math.max(1, Math.trunc(wanted)));

export function processingErrorCode(error) {
  const detail = error?.response?.data?.detail;
  return typeof detail === "string" ? detail : detail?.code || "";
}

export function processingErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail;
  return (typeof detail === "string" ? detail : detail?.message) || error?.message || fallback;
}

export const isCoveragePending = (error) => processingErrorCode(error) === "processing_coverage_pending";
export const isSnapshotExpired = (error) => processingErrorCode(error) === "processing_snapshot_expired";

function targetOf(item) {
  const target = item?.open_target;
  if (!object(target) || !["message", "task", "idea", "review"].includes(target.kind)
      || (typeof target.id !== "number" && typeof target.id !== "string")) {
    throw new TypeError("canonical All item has no supported open_target");
  }
  return { kind: target.kind, id: target.id };
}

export function compactProcessingRow(item) {
  if (!object(item) || typeof item.item_id !== "string" || !item.item_id) {
    throw new TypeError("canonical All item_id must be a non-empty string");
  }
  if (!Array.isArray(item.member_ids) || item.member_ids.some((id) => typeof id !== "string")) {
    throw new TypeError("canonical All member_ids must be strings");
  }
  const target = targetOf(item);
  const counts = object(item.counts) ? { ...item.counts } : {};
  const row = object(item.row) ? { ...item.row } : {};
  const status = typeof item.status === "string" ? item.status : "";
  return {
    ...row,
    ProcessingItemId: item.item_id,
    ProcessingMemberIds: [...item.member_ids],
    ContextRevision: text(item.context_revision),
    ViewRevision: text(item.view_revision),
    ActivityBasis: text(item.activity_basis),
    OpenTarget: target,
    ProcessingCounts: counts,
    SentAt: row.SentAt || item.activity_at || "",
    Subject: row.Subject || item.title || "",
    FromName: row.FromName || item.actor || "",
    Preview: row.Preview || item.preview || "",
    Channel: row.Channel || item.channel || "",
    SourceName: row.SourceName || item.source || "",
    Category: row.Category || item.category || "",
    MsgStatus: row.MsgStatus || status,
    Attachments: row.Attachments ?? counts.attachments ?? 0,
    MessageId: row.MessageId ?? (target.kind === "message" ? target.id : null),
    TaskId: row.TaskId ?? (target.kind === "task" ? target.id : null),
    TaskStatus: row.TaskStatus ?? (target.kind === "task" ? status : null),
    ReviewId: row.ReviewId ?? (target.kind === "review" ? target.id : null),
    IdeaId: row.IdeaId ?? (target.kind === "idea" ? target.id : null),
  };
}

// Unread already arrives as the canonical pile. FeedView needs a small row envelope only for
// its date/count header and for exact-message deep links when "Task" mode is selected; fetching
// the entire canonical All inventory again duplicated the most expensive read on page load.
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
      Unread: item.unread ? 1 : 0,
    }];
  });
}

function validatePage(payload) {
  if (!object(payload) || payload.schema_version !== PROCESSING_ALL_SCHEMA) {
    throw new TypeError("unsupported canonical All response");
  }
  if (typeof payload.snapshot_revision !== "string" || !payload.snapshot_revision) {
    throw new TypeError("canonical All response has no snapshot_revision");
  }
  if (!Array.isArray(payload.items)) throw new TypeError("canonical All items must be an array");
  if (payload.next_cursor != null && typeof payload.next_cursor !== "string") {
    throw new TypeError("canonical All next_cursor must be null or a string");
  }
  const rows = payload.items.map((item) => ({ ...compactProcessingRow(item), AllSnapshotRevision: payload.snapshot_revision }));
  if (!rows.length && payload.next_cursor) throw new TypeError("canonical All empty page cannot have a continuation");
  const ids = rows.map((row) => row.ProcessingItemId);
  if (new Set(ids).size !== ids.length) throw new TypeError("canonical All page contains duplicate item_id values");
  return {
    snapshotRevision: payload.snapshot_revision,
    nextCursor: payload.next_cursor || null,
    counts: object(payload.counts) ? { ...payload.counts } : {},
    coverage: object(payload.coverage) ? structuredClone(payload.coverage) : {},
    rows,
  };
}

export function firstProcessingPage(payload) {
  return validatePage(payload);
}

export function appendProcessingPage(current, payload) {
  const page = validatePage(payload);
  if (!object(current) || current.snapshotRevision !== page.snapshotRevision) {
    throw new TypeError("canonical All page snapshot changed");
  }
  const seen = new Set((current.rows || []).map((row) => row.ProcessingItemId));
  if (page.rows.some((row) => seen.has(row.ProcessingItemId))) {
    throw new TypeError("canonical All pages contain a duplicate item_id");
  }
  return {
    snapshotRevision: current.snapshotRevision,
    nextCursor: page.nextCursor,
    counts: page.counts,
    coverage: page.coverage,
    rows: [...current.rows, ...page.rows],
  };
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
    AllLoadGeneration: compact.AllLoadGeneration ?? null,
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

// The approval interruption (PW-239): the decide answer says the context materially moved, so the
// click did not send. The owner sees the new message and the triage change, keeps their own edit
// for comparison, and gives a fresh yes to the reviewed draft - or cancels. Nothing here sends.
export const INTERRUPT_TITLE = "A new message arrived. Review it before sending.";

export function interruptOf(data, reviewId) {
  if (!data || data.ok || !data.stale || data.already) return null;
  const it = data.interrupt || {};
  return { reviewId, title: it.title || INTERRUPT_TITLE, latest: it.latest || null, triage: it.triage || "",
           yours: it.yours ?? null, refreshed: it.refreshed ?? data.draft ?? null, actions: ["review", "cancel"] };
}

// cancel: the owner's edit stays in the box, nothing else changes. review: the refreshed draft is
// handed over BESIDE the owner's words, never substituted for them - the fresh yes is theirs to give.
export function resolveInterrupt(it, choice, edits) {
  const kept = { ...(edits || {}) };
  if (choice !== "review") return { edits: kept, compare: null, send: false };
  return { edits: kept, compare: { reviewId: it.reviewId, yours: it.yours ?? kept[it.reviewId] ?? "", refreshed: it.refreshed ?? "" }, send: false };
}

// All keeps a selected message exact even when redrafting moves its review to a
// newer member. Keep the attempted edit outside that selection's lifetime.
export function captureInterruptedReply(it, row, text) {
  return { ...it, row: { ...row }, yours: text ?? it.yours ?? "" };
}

export function interruptedReplyTarget(saved, rows) {
  const mid = saved.latest?.MessageId ?? saved.row?.MessageId;
  if (mid == null) throw new Error("The updated reply has no message target. Your edit is saved.");
  const match = (rows || []).find((row) => String(row.MessageId) === String(mid)
    || row.ProcessingMemberIds?.includes(`message:${mid}`));
  const row = match || saved.row;
  // A newly added member may not be in the cached list yet. The canonical detail
  // endpoint verifies membership before returning it; no client-side reassignment.
  return { ...row, MessageId: mid, ...(row?.ProcessingItemId ? { OpenTarget: { kind: "message", id: mid } } : {}) };
}

export function restoreInterruptedReply(saved, loaded) {
  const mid = saved.latest?.MessageId ?? saved.row?.MessageId;
  const row = loaded.row;
  const review = loaded.detail?.reviews?.find((r) => String(r.ReviewId) === String(saved.reviewId)
    && String(r.MessageId) === String(mid) && r.Status === "pending" && r.Kind !== "action");
  if (String(row?.MessageId) !== String(mid) || !review) {
    throw new Error("The updated message no longer owns this pending review. Your edit is saved.");
  }
  return {
    row, yours: saved.yours,
    owner: `${row.ProcessingItemId || `message:${row.MessageId}`}|review:${saved.reviewId}`,
    // An explicit review choice must not show another pending draft for this same message.
    detail: { ...loaded.detail, reviews: [review, ...loaded.detail.reviews.filter((r) =>
      String(r.ReviewId) !== String(saved.reviewId) && (r.Status !== "pending" || r.Kind === "action"))] },
    compare: { reviewId: saved.reviewId, yours: saved.yours, refreshed: review.DraftText ?? "" },
  };
}

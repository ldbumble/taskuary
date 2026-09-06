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

// REPLY OPENS AT ONCE (the owner, 2026-10-01: "Reply opens at once with "Drafting…" and the draft fills in - never waits on
// the AI"). Every Reply press asked /reply to write the draft before it answered, so the card came up only when the model was
// done. Now the box opens (`later`: the review, no model), the card is drawn, and the draft is asked for behind it here - one
// job per review, which whichever card shows that review reads: "Drafting…" while it runs, the draft or the reason after.
import { useSyncExternalStore } from "react";

const jobs = new Map();           // reviewId -> { state: "drafting" | "done" | "failed", draft, error, promise }
const subs = new Set();
const put = (rid, job) => { jobs.set(rid, job); subs.forEach((f) => f()); };
export const draftJob = (rid) => (rid && jobs.get(rid)) || null;
export const subscribeDrafts = (f) => { subs.add(f); return () => subs.delete(f); };
export const useDraftJob = (rid) => useSyncExternalStore(subscribeDrafts, () => draftJob(rid));

// the draft, written behind a card already drawn; a second ask while one runs is the same job
export function draftBehind(api, rid, instruction = null) {
  if (jobs.get(rid)?.state === "drafting") return jobs.get(rid).promise;
  const promise = api.post(`/api/reviews/${rid}/draft`, instruction ? { instruction } : {})
    .then(({ data }) => put(rid, { state: "done", draft: data?.draft || "" }))
    .catch((e) => put(rid, { state: "failed", error: e?.response?.data?.detail || e?.message || "the draft could not be written" }));
  put(rid, { state: "drafting", promise });
  return promise;
}

// THE REPLY PRESS: the box at once, the draft behind it. Resolves with /reply's answer as soon as the review exists.
// `cc`: the people the owner asked to loop in - the server copies the ones it knows and names the ones it does not
// `ai`: Draft with AI was pressed - a plain Reply on a task no agent has worked opens the box empty (server._blank_reply, 2026-10-28)
export async function openReply(api, mid, instruction = null, cc = null, ai = false) {
  const { data } = await api.post(`/api/messages/${mid}/reply`, { draft: true, later: true, instruction, ...(cc?.length ? { cc } : {}), ...(ai ? { ai: true } : {}) });
  if (data?.reviewId && data.drafting) draftBehind(api, data.reviewId, instruction);
  return data;
}

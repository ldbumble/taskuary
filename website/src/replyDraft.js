// REPLY OPENS AT ONCE (the owner, 2026-10-01: "Reply opens at once with "Drafting…" and the draft fills in - never waits on
// the AI"). Every Reply press asked /reply to write the draft before it answered, so the card came up only when the model was
// done. Now the box opens (`later`: the review, no model), the card is drawn, and the draft is asked for behind it here - one
// job per review, which whichever card shows that review reads: "Drafting…" while it runs, the draft or the reason after.
import { useSyncExternalStore } from "react";
import { withSignature } from "./signature.js";

const jobs = new Map();           // reviewId -> { state: "drafting" | "done" | "failed", draft, error, promise }
const subs = new Set();
const put = (rid, job) => { jobs.set(rid, job); subs.forEach((f) => f()); };
export const draftJob = (rid) => (rid && jobs.get(rid)) || null;
export const subscribeDrafts = (f) => { subs.add(f); return () => subs.delete(f); };
export const useDraftJob = (rid) => useSyncExternalStore(subscribeDrafts, () => draftJob(rid));

// the draft, written behind a card already drawn; a second ask while one runs is the same job
// `line`: the Assistant's "Drafting a reply on TQ-n" line - the server says it again with how it went, and `receipt` is that (server._draft_receipt)
export function draftBehind(api, rid, instruction = null, line = null) {
  if (jobs.get(rid)?.state === "drafting") return jobs.get(rid).promise;
  const promise = api.post(`/api/reviews/${rid}/draft`, { ...(instruction ? { instruction } : {}), ...(line ? { line } : {}) })
    .then(({ data }) => put(rid, { state: "done", draft: data?.draft || "", needs: data?.needs || null, receipt: data?.receipt || null }))
    .catch((e) => put(rid, { state: "failed", error: e?.response?.data?.detail || e?.message || "the draft could not be written" }));
  put(rid, { state: "drafting", promise });
  return promise;
}

// A DRAFT BEING WRITTEN leaves its box EMPTY, so it reads "Drafting…" beside the spinner - the signature alone read as a reply left to write.
// The owner's own edit always stands; a redraft keeps the old draft in view until the new one replaces it.
export const boxText = ({ text, draft, drafting, signature }) => text ?? (drafting && !draft ? "" : withSignature(draft, signature));

// A NEW DRAFT FILED UNDER AN OPEN CARD IS SHOWN (2026-11-04): the owner's edit was kept only for the draft it was made on when the card was
// drawn again - a card left open kept its edit over every draft after it, and an emptied box stayed empty under "✓ Rewritten". What the box
// holds once the filed draft changes: the edit held for this new one (another card's, heldOf), else the draft itself (null) - unless the
// owner's edit is being shown beside a refreshed draft (`keep`: the interrupt's compare), which stays theirs
export const editAfterRefile = ({ text, held, keep }) => (keep ? text : held ? held.text : null);

// THE ASSISTANT'S REWRITE RECEIPT says Rewritten only when the review's text changed into something (server._rewritten); otherwise that it
// did not come back, and why. `ref`: the task it landed on when that is not the one below. An older server says no `changed`: its draft decides.
export const rewriteReceipt = (data, ref = "") => (String(data?.draft || "").trim() && data?.changed !== false
  ? { text: ref ? `Rewritten on ${ref} - read it there before you send it.` : "Rewritten - read it below before you send it." }
  : { status: "failed", text: `The rewrite didn't come back${data?.why ? ` - ${data.why}` : ""}. ${ref ? `The draft on ${ref}` : "The draft below"} is as it was - Redraft, or tell me what to say.` });

// THE REPLY PRESS: the box at once, the draft behind it. Resolves with /reply's answer as soon as the review exists.
// `cc`: the people the owner asked to loop in - the server copies the ones it knows and names the ones it does not
// `ai`: Draft with AI was pressed - said for the record; every press that asks for a draft is owed one (server.open_reply, 2026-11-03)
// `line`: the Assistant's under-way line for it, said again by the server once the draft lands or does not (the owner, 2026-11-04)
export async function openReply(api, mid, instruction = null, cc = null, ai = false, line = null) {
  const { data } = await api.post(`/api/messages/${mid}/reply`, { draft: true, later: true, instruction, ...(cc?.length ? { cc } : {}), ...(ai ? { ai: true } : {}),
                                                                  ...(line ? { line } : {}) });
  if (data?.reviewId && data.drafting) draftBehind(api, data.reviewId, instruction, line);
  return data;
}

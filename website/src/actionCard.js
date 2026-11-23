// WHAT THE OWNER PRESSES, AS ITS CONNECTOR DECLARES IT (the owner, 2026-11-05: "each connector should have settings what the action view looks
// like no?"): the catalogue's `actions` (taskuary/connectorcatalog.json) name each act's fields - which the card shows, which the owner may change
// before pressing, and the press words. ActionCard.jsx draws whatever is declared; this is the reading of it, kept apart so it is tested alone.
import { CATALOGUE } from "./connectorCatalog.js";
import { proposalFrom } from "./reviewProposal.js";

const BY_TOOL = Object.fromEntries(CATALOGUE.flatMap((c) => (c.actions || []).filter((a) => a.tool).map((a) => [a.tool, { ...a, card: c.type, title: c.title }])));
export const actionFor = (tool) => BY_TOOL[tool] || null;
export const isCardProposal = (p) => p?.action === "run_tool" && !!actionFor(p?.type);
export const isCardReview = (review) => isCardProposal(proposalFrom(review));
// a review as the card reads it - the shape the assistant payload's `cards` carries (server._assistant_payload): the answered one's FinalText
// holds what went (the owner's edits and the result)
export const cardOf = (review) => {
  if (review?.Kind !== "action") return null;
  let p = null;
  try { p = JSON.parse(review.FinalText || review.DraftText || ""); } catch { return null; }
  const act = isCardProposal(p) ? actionFor(p.type) : null;
  // ...and its connection not made, as the review says it (server _review_connect): the chat's card and this one say Connect alike
  return act ? { ReviewId: review.ReviewId, Status: review.Status, CreatedAt: review.CreatedAt, Reason: review.Reason, ActError: review.ActError,
    post: p, network: act.title, as: "", connect: review.Status === "pending" ? review.Connect || null : null } : null;
};

export const choiceOf = (f, v) => (f?.choices || []).find((c) => String(c.value) === String(v)) || null;
// each declared field with its value - the proposal's, else the catalogue's default - and whether the owner may change it now (only while it waits)
export const fieldsOf = (act, p, live = false) => (act?.fields || []).map((f) => ({ ...f, value: p?.[f.key] ?? f.default ?? "", editable: !!(live && f.edit) }));
export const valuesOf = (act, p) => Object.fromEntries(fieldsOf(act, p).map((f) => [f.key, f.value]));
// the press's words: a picked choice's own ("Save as draft") over the act's ("Post to LinkedIn")
export const wordsOf = (act, values = {}) => {
  const picked = (act?.fields || []).filter((f) => f.type === "choice").map((f) => choiceOf(f, values[f.key])).filter(Boolean);
  const w = (k) => picked.find((c) => c[k])?.[k] || act?.[k] || "";
  return { press: w("press"), busy: w("busy"), done: w("done"), undone: act?.undone || "Not sent" };
};
// only the choices the owner moved off the proposal go with the press: the server takes no other field (connectorcatalog.owner_edits)
export const changed = (act, p, values) => Object.fromEntries((act?.fields || [])
  .filter((f) => f.edit && f.type === "choice" && String(values?.[f.key]) !== String(p?.[f.key] ?? f.default))
  .map((f) => [f.key, values[f.key]]));
// where the card stands: waiting on the press, gone with its words and link, or not gone (`live` false: a caller that only reads it)
export const viaBrowserSaid = (network) => `Handed to the agent - it puts this up on ${network || "the site"} in the browser, and its Post waits for you`;
export const stateOf = (row, live = true) => {
  const s = row?.Status, act = actionFor(row?.post?.type), w = wordsOf(act, row?.post || {});
  // ...a post handed to its agent for the site says so, never "Posted" before anything went up (the owner, 2026-11-22)
  if ((s === "approved" || s === "edited") && row?.post?.result?.browser && !row?.post?.result?.done) return { done: true, said: viaBrowserSaid(row?.network), url: "" };
  if (s === "approved" || s === "edited") return { done: true, said: w.done, url: row?.post?.result?.url || "" };
  if (s === "pending" && live) return { live: true };
  // ...a press that failed is over: its error is the card's line (ActionCard), and its agent sets up what goes next (general.failed)
  if (s === "superseded" && row?.ActError) return { done: false, failed: true, said: "" };
  return { done: false, said: s === "pending" ? w.undone : `${w.undone} · dismissed` };
};
// the box's words: the act's one editable text field (a post's `text`, a tracker comment's `body`)
export const textKey = (act) => (act?.fields || []).find((f) => f.type === "text" && f.edit)?.key || "text";
// the press is lit while the box holds words - or where the act may go without them (`optional`) and the agent left none: Close issue with no
// comment greyed over its empty box was a press nothing could light. Words the agent wrote and the owner emptied still hold it - an empty box
// is never sent as the agent's own (verdicts takes an empty box for the draft)
export const pressable = (act, p, text) => {
  const f = (act?.fields || []).find((x) => x.key === textKey(act));
  return !!String(text || "").trim() || !!(f?.optional && !String(p?.[f.key] ?? "").trim());
};
// the choices a connection keeps its own default for (`setting`), shown on its card under Connections
export const settingsOf = (type) => (CATALOGUE.find((c) => c.type === type)?.actions || []).flatMap((a) => (a.fields || []).filter((f) => f.setting && f.type === "choice"));

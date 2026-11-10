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
  return act ? { ReviewId: review.ReviewId, Status: review.Status, CreatedAt: review.CreatedAt, Reason: review.Reason, post: p, network: act.title, as: "" } : null;
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
export const stateOf = (row, live = true) => {
  const s = row?.Status, act = actionFor(row?.post?.type), w = wordsOf(act, row?.post || {});
  if (s === "approved" || s === "edited") return { done: true, said: w.done, url: row?.post?.result?.url || "" };
  if (s === "pending" && live) return { live: true };
  return { done: false, said: s === "pending" ? w.undone : `${w.undone} · dismissed` };
};
// the box's words: the act's one editable text field (a post's `text`, a tracker comment's `body`)
export const textKey = (act) => (act?.fields || []).find((f) => f.type === "text" && f.edit)?.key || "text";
// the choices a connection keeps its own default for (`setting`), shown on its card under Connections
export const settingsOf = (type) => (CATALOGUE.find((c) => c.type === type)?.actions || []).flatMap((a) => (a.fields || []).filter((f) => f.setting && f.type === "choice"));

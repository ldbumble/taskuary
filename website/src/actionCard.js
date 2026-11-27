// WHAT THE OWNER PRESSES, AS ITS CONNECTOR DECLARES IT (the owner, 2026-11-05: "each connector should have settings what the action view looks
// like no?"): the catalogue's `actions` (taskuary/connectorcatalog.json) name each act's fields - which the card shows, which the owner may change
// before pressing, and the press words. ActionCard.jsx draws whatever is declared; this is the reading of it, kept apart so it is tested alone.
import { CATALOGUE } from "./connectorCatalog.js";
import { proposalFrom } from "./reviewProposal.js";
import { initialsOf } from "./profileAvatar.js";

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
  return act ? { ReviewId: review.ReviewId, Status: review.Status, CreatedAt: review.CreatedAt, Reason: review.Reason, ActError: review.ActError, ActRetry: review.ActRetry, OwnerEdit: review.OwnerEdit, Versions: review.Versions,
    post: p, network: act.title, as: "", connect: review.Status === "pending" ? review.Connect || null : null } : null;
};

// A POST'S PICTURE AS ITS FEED SHOWS IT (the owner, 2026-11-23: "the size it would look like on LinkedIn, the same size as the text"): the words'
// whole width (the card's 12px each side), at its own shape once loaded - a feed's 1.91:1 held for it until then, so nothing jumps - and as tall
// as a feed lets one stand, cropped past that as the feed crops it, rounded as it rounds. Every network's post card draws it so
export const POST_PICTURE = { display: "block", width: "calc(100% - 24px)", height: "auto", aspectRatio: "auto 1.91 / 1", maxHeight: "min(60vh, 560px)",
  objectFit: "cover", mx: 1.5, mt: 0.75, borderRadius: "8px", cursor: "zoom-in" };

// A POST'S FACE IS ITS OWN NETWORK'S (walk 7, 2026-11-23: a Reddit post card wore LinkedIn's "in" - the fallback for a card with no account
// name): the account it goes out as, else the network's own initials - words, never marks ("X (Twitter)" drew "X(", design round 6, D3)
export const faceOf = (row) => { const s = String(row?.as || row?.network || "").trim(); return s ? initialsOf(s) : ""; };
export const choiceOf = (f, v) => (f?.choices || []).find((c) => String(c.value) === String(v)) || null;
// A FIELD AS ITS CARD SAYS IT (connectorcatalog.shown - the card gallery, 2026-11-25: a QuickBooks bill read "amount: 200" and "vendor: Payworth
// (id 58)" in one box under "Write quickbooks bill on QuickBooks Online"): money in its unit, a thing the system runs on an id by its name with
// the id beside it (`ids`), else as given - and the act's title in plain words from its declared `head`
export const shownOf = (f, p, ids = true) => {
  const v = p?.[f?.key];
  if (v == null || v === "") return "";
  if (f.type === "money") { const u = f.unit || "", n = Number(String(v).replaceAll(",", "").replace(u, ""));
    return Number.isFinite(n) ? `${u}${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : String(v); }
  const i = p?.[f.id || ""];
  return ids && i != null && i !== "" ? `${v} (id ${i})` : String(v);
};
export const headOf = (act, p) => String(act?.head || "").replace(/\{(\w+)\}/g, (_, k) => shownOf((act.fields || []).find((f) => f.key === k) || { key: k }, p, false));
// ...an act with no words of its own (a bill: its lines say it all) draws no box, and its lines alone light its press
export const hasBox = (act) => (act?.fields || []).some((f) => f.type === "text");
// each declared field with its value - the proposal's, else the catalogue's default - and whether the owner may change it now (only while it waits)
export const fieldsOf = (act, p, live = false) => (act?.fields || []).map((f) => ({ ...f, value: p?.[f.key] ?? f.default ?? "", editable: !!(live && f.edit) }));
// ...its words' length as its network counts them, against the field's `max` (connectorcatalog.length): a link is `link_counts` where it says
export const lengthOf = (f, text) => String(text ?? "").replace(/https?:\/\/\S+/g, (m) => (f?.link_counts ? "x".repeat(f.link_counts) : m)).length;
export const valuesOf = (act, p) => Object.fromEntries(fieldsOf(act, p).map((f) => [f.key, f.value]));
// the press's words: a picked choice's own ("Save as draft") over the act's ("Post to LinkedIn")
export const wordsOf = (act, values = {}) => {
  const picked = (act?.fields || []).filter((f) => f.type === "choice").map((f) => choiceOf(f, values[f.key])).filter(Boolean);
  const w = (k) => picked.find((c) => c[k])?.[k] || act?.[k] || "";
  return { press: w("press"), busy: w("busy"), done: w("done"), undone: act?.undone || "Not sent" };
};
// ...A WAITING CARD'S WORDS ARE HIS TO CHANGE (the owner, 2026-11-23: "all cards should be that way if there is text"): its box, and each line
// of words its act declares editable (a post's or an issue's title, labels, a content warning) - never where it goes (a repository, an item)
export const isWords = (f) => !!f?.edit && f.type === "line";
// only the choices and lines the owner moved off the proposal go with the press: the server takes no other field (connectorcatalog.owner_edits);
// the box's own words go as its final_text
export const changed = (act, p, values) => Object.fromEntries((act?.fields || [])
  .filter((f) => f.edit && (f.type === "choice" || isWords(f)) && values && f.key in values && String(values[f.key] ?? "") !== String(p?.[f.key] ?? f.default ?? ""))
  .map((f) => [f.key, values[f.key]]));
// THE PRESS SENDS WHAT THE CARD SHOWS (rule 2): the words in its box as he left them, the picks and lines he moved, against the proposal it
// was drawn from (`shown`: one changed since does not run). His no carries none of it
// ...A PRESS THAT FAILED WHERE A SECOND TRY COULD GET PAST IT offers Try again on its failed card, once (the owner, 2026-11-26; ActRetry 1:
// proposals.retryable) - the same press with the words he left, which the server holds. Any other failure is its agent's to get round
export const triesAgain = (row) => row?.Status === "superseded" && !!row?.ActError && row?.ActRetry === 1;
export const pressOf = (verb, act, p, text, values) => {
  const moved = verb === "approve" ? changed(act, p, values) : {};
  return { verb, final_text: verb === "approve" ? text : null, shown: p, ...(Object.keys(moved).length ? { fields: moved } : {}) };
};
// ...and the card reads what he pressed - his words, his picks - wherever the press ended: gone, or failed
export const asLeft = (act, p, text, values) => ({ ...p, ...values, [textKey(act)]: text });
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
// is never sent as the agent's own (verdicts takes an empty box for the draft). ...And a line he emptied that the act cannot go without (an
// issue's title) holds it too: the server refuses it (owner_edits)
export const pressable = (act, p, text, values = {}) => {
  const f = (act?.fields || []).find((x) => x.key === textKey(act));
  const lines = (act?.fields || []).filter((x) => isWords(x) && !x.optional && x.key in values).every((x) => String(values[x.key] ?? "").trim());
  return lines && (!hasBox(act) || !!String(text || "").trim() || !!(f?.optional && !String(p?.[f.key] ?? "").trim()));
};
// the choices a connection keeps its own default for (`setting`), shown on its card under Connections
export const settingsOf = (type) => (CATALOGUE.find((c) => c.type === type)?.actions || []).flatMap((a) => (a.fields || []).filter((f) => f.setting && f.type === "choice"));

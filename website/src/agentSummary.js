// WHERE THE OWNER STANDS AFTER A TURN (general.SUMMARY_TYPE, Task 3.5): each answer may carry `summary` = {about, did, on_you, nothing_left},
// drawn as "What this is about" / "What I did" / "Next steps" (AgentSummary.jsx). Dependency-free so it runs under bare node.

// a reply drafted and not yet sent - an action (a playbook, a held browser act) or a slot email is not one
const isDraft = (r) => !!r && r.Kind !== "action" && r.Kind !== "slot" && r.Status === "pending";

// the newest summary stays open; every earlier one folds to what it did
// ...and when the newest answer has no summary of its own, every one folds: the cards then follow that answer (GeneralWorkspace `lastSummed`),
// never an older turn's summary up the chat (the owner, 2026-11-05: "where is the email ui to send it out?")
// THE DRAFT CARD IS PART OF ITS TURN (the owner, 2026-11-05: "the draft card is part of the chat response. So if i ask new question that is no
// longer applicable. if i ask to update to new email a new email ui pops up. it's part of that taskuary turn. next turn if i ask something or new
// input that turn is gone ... think chatting with assistant"): only the turn that is the LAST entry carries it. Anything after it - the owner's
// words, a mail - makes it history: it folds, its card goes, and the turn that answers draws its own card if it drafts one
export const lastAnswerSummed = (messages) => { const m = (messages || []).filter((x) => x && !x.held).at(-1); return !!m?.summary; };
export const turnIsLast = (messages, id) => (messages || []).filter((x) => x && !x.held).at(-1)?.id === id;
export const foldedSummaries = (messages) => {
  const ids = (messages || []).filter((m) => m?.summary).map((m) => m.id);
  return new Set(lastAnswerSummed(messages) ? ids.slice(0, -1) : ids);
};

const isHeld = (r) => !!r && r.Kind === "action" && r.Status === "pending";

// what is left: the drafts waiting on Send (only where the cards are drawn), the owner's unticked On you steps from the checklist (store.set_on_you
// keeps them there, so a tick counts at once), what waits on Approve - a held browser act, a playbook drafted here (`acts`, the chat's own, with
// the task's pending actions, each once) - and "nothing left" only when the agent said so AND nothing above waits
export const nextSteps = ({ summary, reviews = [], checklist = [], acts = [], cards = true } = {}) => {
  const drafts = cards ? (reviews || []).filter(isDraft) : [], onYou = (checklist || []).filter((i) => i?.on_you && !i.done && i.text);
  const held = [...new Map([...(reviews || []), ...(acts || [])].filter(isHeld).map((r) => [r.ReviewId, r])).values()];
  return { drafts, onYou, held, nothing: !drafts.length && !onYou.length && !held.length && !!summary?.nothing_left };
};

// A REPLY OWED IS NOT A SUGGESTED REPLY (the owner's stress run, 2026-11-05): while the agent worked, the chat drew "Suggested reply" over a
// bare "To Ray Colton" with nothing under it - the envelope of a reply nobody had written yet. In the chat the reply's place stands once there
// is a reply in it: a draft waiting, or one that was sent or closed unsent
export const chatReplyShown = ({ replyMessage, pendingReview, sentReview, unsentReview } = {}) =>
  !!replyMessage && !!(pendingReview || sentReview || unsentReview);

// ...and "Suggested reply" heads Close out's body in the chat only over a reply - a draft, or one sent or closed unsent. Over a closed task's
// "✓ Mark done just now" it named a reply there never was (the stress run's browser task, 2026-11-05)
export const hasReply = (reviews) => (reviews || []).some((r) => r && r.Kind !== "action" && r.Kind !== "slot");
// IS THE AGENT'S PROSE THE RESULT? The agent says so itself (the owner, 2026-11-05: "no hardcoded words; the model reads intent"): its summary's
// `answer_is_result`. A turn filed before it could say - or one that did not - reads by the length-or-link rule the pane used until then, so
// history draws as it always did
const answerWords = (w) => { const t = String(w || "").trim(); return !!t && (t.length <= 500 || /https?:\/\/|\b[A-Za-z]:\\|(^|\s)\/(Users|home|mnt|tmp)\/|\\\\\S+/.test(t)); };
export const answerShown = (summary, words) => !String(words || "").trim() ? false
  : typeof summary?.answer_is_result === "boolean" ? summary.answer_is_result : answerWords(words);

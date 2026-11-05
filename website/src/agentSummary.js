// WHERE THE OWNER STANDS AFTER A TURN (general.SUMMARY_TYPE, Task 3.5): each answer may carry `summary` = {about, did, on_you, nothing_left},
// drawn as "What this is about" / "What I did" / "Next steps" (AgentSummary.jsx). Dependency-free so it runs under bare node.

// a reply drafted and not yet sent - an action (a playbook, a held browser act) or a slot email is not one
const isDraft = (r) => !!r && r.Kind !== "action" && r.Kind !== "slot" && r.Status === "pending";

// the newest summary stays open; every earlier one folds to what it did
export const foldedSummaries = (messages) => new Set((messages || []).filter((m) => m?.summary).map((m) => m.id).slice(0, -1));

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

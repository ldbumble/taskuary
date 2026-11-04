// WHERE THE OWNER STANDS AFTER A TURN (general.SUMMARY_TYPE, Task 3.5): each answer may carry `summary` = {about, did, on_you, nothing_left},
// drawn as "What this is about" / "What I did" / "Next steps" (AgentSummary.jsx). Dependency-free so it runs under bare node.

// a reply drafted and not yet sent - an action (a playbook, a held browser act) or a slot email is not one
const isDraft = (r) => !!r && r.Kind !== "action" && r.Kind !== "slot" && r.Status === "pending";

// the newest summary stays open; every earlier one folds to what it did
export const foldedSummaries = (messages) => new Set((messages || []).filter((m) => m?.summary).map((m) => m.id).slice(0, -1));

// what is left: the drafts waiting on Send (only where the cards are drawn), the owner's unticked On you steps from the checklist (store.set_on_you
// keeps them there, so a tick counts at once), and "nothing left" only when the agent said so AND nothing above waits
export const nextSteps = ({ summary, reviews = [], checklist = [], cards = true } = {}) => {
  const drafts = cards ? (reviews || []).filter(isDraft) : [], onYou = (checklist || []).filter((i) => i?.on_you && !i.done && i.text);
  return { drafts, onYou, nothing: !drafts.length && !onYou.length && !!summary?.nothing_left };
};

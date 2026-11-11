// WHERE THE OWNER STANDS AFTER A TURN (general.SUMMARY_TYPE, Task 3.5): each answer may carry `summary` = {about, did, on_you, nothing_left},
// drawn as "What this is about" / "What I did" / "Next steps" (AgentSummary.jsx). No React, so it runs under bare node.
import { asUtc } from "./dates.js";

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
// A NOTHING-NEW TURN IS ONE LINE (the owner, 2026-11-06: "Ray thanked you." - no three parts, the earlier draft not redrawn): the agent judges it
// and files a summary with only `did`, one line - no `about`, no steps, no draft of its own (selfclose.SUMMARY_LINE, ingest.REPLAN)
export const oneLine = (s) => { const did = String(s?.did || "").trim();
  return !!did && !did.includes("\n") &&!String(s?.about || "").trim() && !(s?.on_you || []).length && !(s?.drafted || []).length; };
export const foldedSummaries = (messages) => {
  const ms = (messages || []).filter((m) => m?.summary), ids = ms.map((m) => m.id);
  if (!lastAnswerSummed(messages)) return new Set(ids);
  // ...and one-line turns after a real answer leave it open, its draft and Send where they were: they answered nothing to fold it under
  const real = ms.findLastIndex((m) => !oneLine(m.summary)), keep = new Set([ids.at(-1), ...(ms.slice(real + 1).every((m) => oneLine(m.summary)) && real >= 0 ? [ids[real]] : [])]);
  return new Set(ids.filter((id) => !keep.has(id)));
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
// a turn whose agent said something of its own: those words are the turn, and the summary's prose is not drawn beside them (AgentSummary `answered`)
export const turnAnswered = (words) => !!String(words || "").trim();
export const answerShown = (summary, words) => !String(words || "").trim() ? false
  : typeof summary?.answer_is_result === "boolean" ? summary.answer_is_result : answerWords(words);

// A DRAFT UNDER ITS OWN TURN (latest-wins): the chat payload says, per pending draft, the turn that wrote it (`turn`, its message id) and whether
// it is `stale` - made before the owner's newest message - with its time. A stale one stays on its turn with a quiet line, and never stands
// under the newest turn's Next steps. Read with defaults, so a payload without them draws as before
export const draftTurn = (r) => r?.turn ?? r?.Turn ?? null;
export const staleDraft = (r) => !!(r?.stale ?? r?.Stale);
const pendingReply = (r) => r?.Status === "pending" && r.Kind !== "action" && r.Kind !== "slot" && String(r.DraftText || "").trim();
// ...the newest turn's Next steps hold the drafts only while one of them is fresh
export const freshNext = (reviews) => { const ps = (reviews || []).filter(pendingReply); return !ps.length || ps.some((r) => !staleDraft(r)); };
// ...AND ON A CODING TASK TOO (the owner, 2026-11-09: "it also disappeared once i asked next question. i thought actions stay on the past
// prompt"): its chat is the CLI's sessions (codingchat.py), whose payload names no turn per draft, so every draft read "no shown turn wrote
// one" and the card rode under whichever turn was newest. Its turn is the one at work when it was written: the newest agent turn started at
// or before the draft's time (both stamps the server's own zone). Stale as general.draft_turns reads it: an owner's line came after it and no
// turn has answered since. The same {review, turn, at, stale, before} the general chat's payload carries
const stamp = (x) => String(x || "").replace("T", " ").slice(0, 19);
export const codingDrafts = (reviews, messages) => {
  const ms = (messages || []).filter((m) => m && m.createdAt), turns = ms.filter((m) => m.role === "assistant"), mine = ms.filter((m) => m.role === "user" && !m.brief);
  return (reviews || []).filter(pendingReply).map((r) => {
    const at = stamp(r.CreatedAt), turn = turns.filter((m) => stamp(m.createdAt) <= at).at(-1);
    const later = mine.map((m) => stamp(m.createdAt)).filter((t) => t > at).sort()[0];
    const stale = !!later && !turns.some((m) => stamp(m.createdAt) > later);
    return { review: r.ReviewId, turn: turn ? String(turn.id) : null, at, stale, before: stale ? later : null };
  });
};
// EVERY OTHER CARD OF THE TASK IN THE TURN THAT RAISED IT (TaskPage's turnCards: a held steps' card, a reply that went, an ask that waits).
// On a coding chat that is the newest agent turn begun at or before it (`turnOf` - the thread's times are Dates, the server's stamps read as
// they are). IN A GENERAL CHAT THE SERVER NAMES IT (the payload's `turns`, by the review `rid`; the spine audit, 2026-11-09): an answer there
// is stamped when its turn ENDS, so that rule read a step held while the second turn worked into the first. Named with no answer yet: null,
// the chat's foot. A coding chat's payload names none, and an answer the thread does not draw is no place to stand - turnOf
const msOf = (x) => (x instanceof Date ? +x : +(String(x).includes("Z") ? new Date(x) : asUtc(String(x))));
export const turnOf = (messages, at) => {
  const turns = (messages || []).filter((m) => m?.role === "assistant" && m.id), t = msOf(at);
  return turns.length ? (turns.filter((m) => m.createdAt && msOf(m.createdAt) <= t).at(-1) || turns.at(-1)).id : null;
};
// ...and NEVER AT THE FOOT (the owner, 2026-11-10: "it's just a row in the chat"): a card the server names no answered turn for was raised by the
// turn still at work - the newest - and one whose named turn is not drawn stands by its time
// ...`byRow`: a card that stands where something before it stood - a replaced draft's record - goes by its time among every row (rowOf)
export const placeCards = (cards, messages, turns) => { const ids = new Set((messages || []).map((m) => m.id));
  const newest = (messages || []).filter((m) => m?.role === "assistant" && m.id).at(-1)?.id || null;
  return (cards || []).map((c) => { const named = turns && c.rid != null ? turns[c.rid] ?? null : undefined;
    return { ...c, after: named && ids.has(named) ? named : c.byRow ? rowOf(messages, c.at) : named === null ? newest : turnOf(messages, c.at) }; }); };
// THE ROW A DRAFT STANDS AFTER, BY TIME (the owner, 2026-11-10: "i asked it to rewrite a email, it reqrote in place then put it under the prompt"):
// the last row of the chat - the mail come in, a line of his, an answer - drawn at or before it. A reply drafted on arrival stood at the chat's
// foot, so the line he typed went over it and the card jumped under his line; under the mail it answers it stays where it was
// ...a row with no time yet - the turn at work, drawn before its answer is filed - is as old as the row before it: a draft written while it works
// is its own, never his line's (the recorded walk, 2026-11-10: the new card stood under his line, over the turn's head, then jumped into the turn)
// ...and AN ANSWER IS AS OLD AS ITS TURN'S START, the row before it: it is stamped when the turn ENDS, so the moment it was filed - before the
// server named it the draft's turn - the draft its turn wrote read as older and stood a beat over its head (the recorded walk, 2026-11-10)
export const rowOf = (messages, at) => { const t = msOf(at); let was = -Infinity, id = null;
  for (const m of messages || []) { if (!m?.id) continue; const own = m.createdAt ? msOf(m.createdAt) : was;
    if ((m.role === "assistant" ? was : own) <= t) id = m.id; was = own; }
  return id; };
// ...a reply, or an email the task owes (a slot's card, slots.draft) - both are the draft card the owner rewrites by prompting
const letter = (r) => r?.Status === "pending" && r.Kind !== "action" && String(r.DraftText || "").trim();
const waitingDraft = (reviews) => (reviews || []).filter(letter).sort((a, b) => a.ReviewId - b.ReviewId).at(-1) || null;
// ...the waiting draft's place: the turn that wrote it where the chat draws that turn, else its row by time
export const draftHome = (reviews, messages) => {
  const r = waitingDraft(reviews), t = r && draftTurn(r);
  if (!r) return null;
  return t != null && (messages || []).some((m) => String(m.id) === String(t)) ? String(t) : rowOf(messages, r.CreatedAt);
};
// ...AND OLD NEWS FROM THE PRESS (the owner, 2026-11-10: "The second you write ptompt on email action it should go gray"): a line of his newer
// than the draft - in the thread, as the runtime draws it the paint he presses, or held on the page (`pressed`, ms) - or the server's word that
// one came (`stale`). Greyed where it stands, its words as they were and its Send off; what the agent writes after is a new card in its turn
const ownLine = (m) => m?.role === "user" && !(m.brief || m.metadata?.custom?.brief || m.press || m.metadata?.custom?.press);
export const draftPassed = (reviews, messages, pressed = 0) => {
  const r = waitingDraft(reviews);
  if (!r) return false;
  const t = msOf(r.CreatedAt);
  return staleDraft(r) || (pressed > t) || (messages || []).some((m) => ownLine(m) && m.createdAt && msOf(m.createdAt) > t);
};
// ...the payload's `drafts` (general.draft_turns: {review, turn, at, stale, before}) read onto the reviews they name
export const withTurns = (reviews, drafts) => (drafts?.length ? (reviews || []).map((r) => { const d = drafts.find((x) => x?.review === r?.ReviewId);
  return d ? { ...r, turn: d.turn, stale: !!d.stale, drafted_at: d.at, before: d.before } : r; }) : reviews || []);

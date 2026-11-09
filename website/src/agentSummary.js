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
export const draftAt = (r) => r?.drafted_at ?? r?.DraftedAt ?? r?.at ?? "";
const pendingReply = (r) => r?.Status === "pending" && r.Kind !== "action" && r.Kind !== "slot" && String(r.DraftText || "").trim();
// ...the newest turn's Next steps hold the drafts only while one of them is fresh
export const freshNext = (reviews) => { const ps = (reviews || []).filter(pendingReply); return !ps.length || ps.some((r) => !staleDraft(r)); };
export const staleOn = (reviews, turnId) => (reviews || []).filter((r) => pendingReply(r) && staleDraft(r) && turnId != null && String(draftTurn(r)) === String(turnId));
// THE LIVE CARD STAYS ON THE TURN THAT WROTE IT (the owner, 2026-11-09: "again suggested reply stayed on bottom after i asked it questions"): a
// draft the agent KEPT through later turns is current with its Send (general.draft_turns, 2026-11-08), and it followed whichever turn was newest -
// under every question asked since. Its home is the turn that last wrote it (a rewrite moves it there, a new letter replaces it); null when no
// shown turn wrote one, and the newest answer holds the cards as before
export const cardTurn = (reviews, ids) => { const on = new Set((ids || []).map(String));
  const r = (reviews || []).filter((x) => pendingReply(x) && !staleDraft(x) && on.has(String(draftTurn(x)))).sort((a, b) => a.ReviewId - b.ReviewId).at(-1);
  return r ? String(draftTurn(r)) : null; };
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
// ...the payload's `drafts` (general.draft_turns: {review, turn, at, stale, before}) read onto the reviews they name
export const withTurns = (reviews, drafts) => (drafts?.length ? (reviews || []).map((r) => { const d = drafts.find((x) => x?.review === r?.ReviewId);
  return d ? { ...r, turn: d.turn, stale: !!d.stale, drafted_at: d.at, before: d.before } : r; }) : reviews || []);

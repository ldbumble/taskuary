// THE TASK'S OWN MOVES, ONE TOOLBAR FOR EVERY STATE (the owner, 2026-11-23, walk 11 F7: held for a stranger the row read "Close with a note / Find
// a time / Share / ▾", with an agent at work "Change ▾" and none of those - the toolbar was built per state). What acts on the whole task is the
// same buttons, in the same words and the same order, whatever the task is doing: held, at work, after a restart, at rest or closed. A move that
// does not apply now stands greyed and says why - never gone - and what is lit is the task's own pick. A closed task's Reopen stands in Mark
// done's place. The agent's stage moves (Send to agent, Continue, Review changes) and a calendar's answers come with what they act on.
// `s`: the task's state - { closed, live, reopening, finishing, waitingDraft, watching, away (its Remind me's "Back <day>"), manual (no AI:
// Hand it to a person stands), repo: { held, can, set }, trust: { label, busy } (held for a sender he has not trusted) }; `run`: the page's
// handler for each move; `w`: its words ({ label, hint, doneHint }). `s.closedWith`: the move that closed it here ("done" | "close-note") - while he
// stays on the task its result stands greyed beside Reopen ("✓ Done"), where it used to vanish with Mark done the moment the closed row drew
import { pressWord } from "./pressResult.js";
const CLOSED = "the task is closed - reopen it first";
const LIVE = "an agent is working - Mark done stops it and closes the task";
// ...AND AN ITEM TASKUARY MADE (madeTask.js: a report, a dashboard, an Advisor idea) is drawn by the same page with ITS moves, from this same
// builder, in one order: its own move (an idea's Connect, a failed run's Run it again), Pause, Make it a task, Remind me, Not for me - the words
// its row is served (concierge.chips_for), each its press. Share is the page's own (useShareParts); starting an agent is the chat's box
// `s.made`: [{ verb, label, title, disabled, onClick, own }] - `own` lit
const MADE_ORDER = ["rerun", "report_off", "mine", "defer", "watch", "not_ours"], MADE_STARTS = new Set(["regular_agent", "coding_agent", "next"]);
const madeMoves = (words) => words.filter((a) => !MADE_STARTS.has(a.verb))
  .sort((a, b) => (b.own ? 1 : 0) - (a.own ? 1 : 0) || (MADE_ORDER.indexOf(a.verb) + 1 || 99) - (MADE_ORDER.indexOf(b.verb) + 1 || 99))
  .map((a, i) => ({ id: `w:${a.verb || a.label}`, group: a.own || i < 3 ? "decide" : "more", tone: a.own ? "p" : "s", label: a.label, title: a.title,
    ...(a.disabled ? { disabled: true, why: a.title || "" } : {}), run: (e, anchor) => a.onClick?.({ currentTarget: anchor || e?.currentTarget }) }));
export function taskMoves(s, run, w) {
  if (s.made) return madeMoves(s.made);
  const off = (why) => (why ? { disabled: true, why } : {}), shut = off(s.closed ? CLOSED : "");
  return [
    // A TASK HELD FOR A SENDER HE HAS NOT TRUSTED IS UNBLOCKED BY ONE PRESS, LIT ON THE ROW (walk 14, 2026-11-24: opened from the rail its Trust sat in
    // the folded Agent pane, "Agent not started", and nothing on screen moved it) - the row's own move, as a start held for a repository is
    ...(s.trust && !s.closed ? [{ id: "trust", group: "decide", tone: "p", unblocks: true, label: s.trust.busy ? "Starting…" : s.trust.label, run: run.trust,
      ...off(s.trust.busy ? "it is starting" : ""), title: s.trust.hint }] : []),
    ...(s.closed && pressWord(s.closedWith) ? [{ id: "closed-result", group: "decide", tone: "s", label: `✓ ${pressWord(s.closedWith)}`, result: true, disabled: true,
      why: "you closed it - Reopen brings it back" }] : []),
    s.closed
      ? { id: "reopen", group: "decide", tone: "s", label: s.reopening ? "Reopening…" : w.label("reopen"), run: run.reopen, ...off(s.reopening ? "it is reopening" : ""), title: w.hint("reopen") }
      // ...a live session has no primary; nor a waiting draft: its Send, under the draft, is the move (2026-10-06), so Mark done stands outlined
      : { id: "done", group: "more", label: s.finishing ? "Marking done…" : w.label("done"), ...off(s.finishing ? "it is closing" : ""), run: run.done, title: w.doneHint,
        promote: !s.live && !s.waitingDraft && !s.trust, beside: s.live, onCard: s.waitingDraft && !s.live },
    // ...Mark done with words: its card opens in the conversation, under the item
    { id: "close-note", group: "more", label: w.label("close-note"), run: run.note, title: w.hint("close-note"), ...off(s.closed ? CLOSED : s.live ? LIVE : "") },
    // ONE VERB FOR IT, button and dialog (U13)
    { id: "nat", group: "more", label: w.label("nat"), run: run.nat, title: w.natTitle, ...shut },
    { id: "remind", group: "more", label: s.away || w.label("remind"), run: run.remind, title: w.hint("remind"), ...shut },
    { id: "watch", group: "more", label: w.label("watch", s.watching ? "on" : null), run: run.watch, title: w.hint("watch", s.watching ? "on" : null), ...shut },
    ...(s.manual ? [{ id: "hand", group: "more", label: w.label("hand"), run: run.hand, title: w.hint("hand"), tucked: true, ...shut }] : []),
    { id: "reshape", group: "more", label: w.label("reshape"), run: run.reshape, title: w.hint("reshape"), ...shut },
    // WHAT THE PILLS USED TO CHANGE (section 1's redesign, 2026-10-16): the same PATCHes and the same repository picker, each a menu at the row's button
    { id: "kind", group: "more", label: w.label("kind"), run: run.kind, title: w.hint("kind"), ...shut },
    { id: "priority", group: "more", label: w.label("priority"), run: run.priority, title: w.hint("priority"), ...shut },
    // ...a repository is a coding tool's question; a start HELD for it is the row's own move, not a More item
    ...(s.repo?.held || s.repo?.can ? [{ id: "repo", group: s.repo.held && !s.closed ? "decide" : "more", tone: s.repo.held && !s.closed ? "p" : undefined, unblocks: !!s.repo.held && !s.closed,
      label: w.repo, run: run.repo, title: w.repoHint, ...shut }] : []),
  ];
}

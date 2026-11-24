// A ROW'S STATUS, SAID ONCE (the task page redesign, owner-approved 2026-10-21): the rail row's icon and the task page's header pill
// draw the SAME mark and word for one task, from taskuary/lanes.json through the rail's own reading (funnelPile.rowMeta) - so the two
// cannot disagree. The spinning ring is an agent at work; a hand or a flag on the logo is the owner's move; every other state is the
// plain logo, its words in the icon's label.
// Pure, so node --test reads it.
import { KIND_META, rowMeta, taskStateMeta } from "./funnelPile.js";

// THE ONLY BADGES (the owner, 2026-10-22: too many emojis on the rail): the hand of somebody - or an agent - waiting on you, which
// waves, and the flag of a reply ready to send. Every other state is the plain logo; its words are the icon's label and hover.
export const BADGE = { blocked: "👋", asked: "👋", approve: "🏁" };
// where a badge moves: the hand waves; the flag holds still. `ring` is the agent at work.
export const ANIM = { blocked: "wave", asked: "wave" };

const said = (key, m, spins) => ({ key, mark: m.mark, word: m.word, role: m.role ?? null, hint: m.hint || "", spins,
  badge: spins ? "" : BADGE[key] || "", anim: spins ? "ring" : ANIM[key] || null });

// a RAIL ROW (a funnel item: lane, kind, not_sent, settling) as the rail draws it - a kind's word over its lane's, a refused send over both
// ...and A DRAFT ITS CHANNEL CANNOT SEND (`cantSend`: capabilities.canSend / draftCanSend, the caller's live answer) is no flag and no
// "ready to send": a Teams row wore both over a reply nothing here can send (the UI walk, 2026-10-22) - it is a draft to copy
const UNSENDABLE = "unsendable";
// AN AGENT LANE IS A CLAIM ABOUT A LIVE SESSION, and a newer read of the task can take it back (the owner, 2026-10-23: "this shows agent
// working but it's not working"). An agent finished, its pty closed, its reply waited in Close out - and the rail row and the header pill
// said "agent working" for seven minutes, from a rail built while it worked, beside a Result that said it had finished. `page`: the
// task's own read when it was asked after the rail's (taskDetail.pageRead) - no live session, and a state past the agent's work - and
// then that state is the row's: ready to send, agent finished, stopped. The rail's own words stand for every other lane.
const AGENT_LANES = new Set(["working", "blocked"]);
export const agentGone = (item, page) => !!page && AGENT_LANES.has(item?.lane) && !page.live && !!page.state && !AGENT_LANES.has(page.state)
  && !!taskStateMeta(page.state);
// A REPLY OWED WITH NO DRAFT YET is no flag and no "ready to send" (the owner, 2026-10-27): the rail, the header and the phone said
// "ready to send" over a reply nothing had written - it reads "reply owed" until the draft lands (funnel: `draft: false`)
const OWED = "owed";
export const owedNoDraft = (item) => item?.lane === "approve" && item.kind === "review" && item.draft === false && !item.not_sent;
// A CHAT TASK'S WAITING MOVE IS THE AGENT'S (the owner, 2026-11-05: "we can remove reply ready for you since it can be any action"): its
// "agent waiting on you" and "ready to send" both say "agent ready for you" (lanes.json `chat_ready`; funnel marks the row `chat`) - the
// lane, its badge and its rules stay; only the words change. A coding task keeps its own
// ...AND ONE CYCLE (the owner, 2026-11-06): agent working -> agent waiting on you (it answered or drafted) -> after you Send, "agent done"
// (lanes.json `chat_done`; the server's taskstate.chat_moved_on marks the row `chat_done` and the task `agentdone`) -> typed to again, working.
// The rail's icon, the header's chip and the Tasks list all read it here
const CHAT_READY = new Set(["blocked", "approve"]), CHAT_DONE = new Set(["agentdone", "wrapup", "chat_done"]);
const chatDone = (st) => ({ ...st, key: "chat_done", word: KIND_META.chat_done.word, hint: KIND_META.chat_done.hint, mark: KIND_META.chat_done.mark,
  role: KIND_META.chat_done.role, badge: "", anim: null, spins: false });
export const chatReady = (st, chat) => (!chat || !st ? st : CHAT_READY.has(st.key) ? { ...st, word: KIND_META.chat_ready.word, hint: KIND_META.chat_ready.hint }
  : CHAT_DONE.has(st.key) ? chatDone(st) : st);
// ...and WHETHER A TASK READS AS A CHAT is its rail row's word where it has one (the rail walk, 2026-11-12: a general task with a reply
// drafted read "ready to send" on its row and "agent waiting on you" in its header - the header took any general task as a chat); a task
// off the rail falls back to its kind
export const chatOf = (rail, general = false) => (rail ? !!(rail.chat || rail.chat_done) : !!general);
export const railStatus = (item, cantSend = false, page = null) => chatReady(railStatus_(item, cantSend, page), !!item?.chat || !!item?.chat_done);
const railStatus_ = (item, cantSend = false, page = null) => {
  if (agentGone(item, page)) return taskStatus({ state: page.state, cantSend });
  if (!item?.lane) return null;
  if (owedNoDraft(item)) return said(OWED, { ...rowMeta(item), ...KIND_META[OWED] }, false);
  const copy = cantSend && !item.not_sent && item.lane === "approve" && item.kind === "review";
  // ...a FINISHED run's row (processing_unread: lane yours, `finished`) is the agent's finish, as its line says: the pill read "on you"
  // under "the assistant finished - read what it found" (the product audit, 2026-11-08) - as the server's state_of says it
  const done = item.finished && item.lane === "yours" && !KIND_META[item.kind];
  const key = copy ? UNSENDABLE : item.not_sent ? "not_sent" : item.hold ? "held" : done ? "agentdone" : KIND_META[item.kind] ? item.kind : item.lane;
  const spins = item.lane === "working" && !item.settling;
  // ...and the server's words for the very state it read (funnel.one_state: taskstate.status) - whose input it waits for, by name
  const own = item.status?.key === key && item.status.word ? { word: item.status.word } : {};
  return said(key, copy ? { ...rowMeta(item), ...KIND_META[UNSENDABLE] } : done ? { ...rowMeta(item), ...KIND_META.agentdone } : { ...rowMeta(item), ...own }, spins);

};
// ...and the line under the row on the table: the rail's `why` ("An agent is working on this ...") goes with the lane it explains
// ...but A ROW WITH NOTHING LIT SAYS WHY in its state's own sentence (the owner, 2026-11-10: "if it's consistent do it"): the server's
// line for it (rulebook.recommended `unlit`, the line advisor.decide gives the phone), the same words on the row, the task and the phone
export const unlitWhy = (rec) => (rec && !rec.verb && rec.why) || "";
export const rowWhy = (item, page = null) => (agentGone(item, page) ? taskStateMeta(page.state)?.hint || "" : unlitWhy(item?.recommended) || item?.why || "");
// a TASK'S STATE (taskstate.py: a lane, or `theirs`, `agentdone`, `closed`, `dropped`) - the Tasks list's row, and a task with no rail row
export const stateStatus = (key) => {
  const m = key && taskStateMeta(key);
  return m ? said(key, m, key === "working") : null;
};

// THE SERVER'S STATUS FOR THE TASK (taskstate.status, the roads audit 2026-11-19 #9): its key and its words, said once on the server - the
// chat's words, a reply owed and a start that failed already read there - drawn as given, with the rail's mark, badge and ring over it
export const fromServer = (s) => (s?.key ? said(s.key, { ...(taskStateMeta(s.key) || {}), word: s.word, hint: s.hint || "", ...(s.mark ? { mark: s.mark } : {}) }, !!s.spins) : null);

// THE TASK PAGE'S STATUS: the live session's own word first - the rail's working and waiting lanes read that very session (taskstate:
// a live session is `blocked` when it waits, else `working`) - then the rail's row for the task (on the canvas), then the server's state
// (the Tasks list's row, or the detail's own for a task with no row - a closed one).
// A CLOSED task has no rail row of its own - one pulled onto the table by a link or a search wears whatever lane it was read in - so
// its state is the server's: done, the agent finished, or dropped.
// `cantSend`: the task's pending draft cannot leave from here (TaskPage's cantSend) - its pill is the rail's "draft to copy", not the flag
// `page`: the task's own read, newer than the rail's (agentGone) - the same reading the rail row takes, so the two still cannot disagree
// `owed`: whether the task's pending reply has no draft yet (TaskPage's pendingReview; null when it has none) - the task's own read
// is newer than the rail's, so a draft that just landed lifts "reply owed" and one not written yet puts it there
// `chat`: the task is a general chat task (chatReady)
// `queued`: the task's dispatch-queue row - a start that FAILED says "couldn't start", never "waiting to start" (the owner, 2026-11-06)
export const taskStatus = ({ chat = false, queued = null, ...o } = {}) => {
  // ...a turn Taskuary tries again by itself is its own, never his (the judge's look, 2026-11-20: "agent waiting on you" over it) - taskstate.status
  if (queued?.retryTurn && queued.state === "retrying" && !o.live?.working) return said("retrying", KIND_META.retrying, false);
  const st = chatReady(taskStatus_({ ...o, chat }), chat);
  return st?.key === "queued" && queued?.state === "failed" ? said("start_failed", KIND_META.start_failed, false) : st;
};
// `server`: the task's own status from its detail (fromServer) - where the page had no rail row it read the state key and laid the chat's,
// the owed and the failed start's words over it itself; the server says them now, and the key is the fallback for a detail without one
const taskStatus_ = ({ live = null, rail = null, state = null, closed = false, cantSend = false, page = null, owed = null, chat = false, server = null } = {}) => {
  // ...unless the server read the parked session as the reply it drafted waiting (taskstate: `approve`) - one state, as the Board's - or a
  // chat agent the owner already answered as done for now (`agentdone`, taskstate.chat_moved_on)
  // ...any agent's, since 2026-11-10: a coding agent that pushed and said nothing is left read "agent waiting on you" (taskstate.done_for_now)
  // ...AND AN AGENT AT REST IS WHAT THE SERVER SAYS IT IS (round 3, 2026-11-22: after his Stop, a killed agent, an email card waiting - the
  // server said "agent stopped", the page drew "waiting on you" off the live session): at work is the live session's to say, the freshest fact;
  // at rest, the task's one state (taskstate.status) - "waiting on you" only where the server reads it so
  if (live?.alive && !live.waiting) return railStatus({ lane: "working" });
  const own = fromServer(server) || stateStatus(state);
  if (live?.alive && state === "agentdone") return chatDone(stateStatus(state));
  if (live?.alive && state !== "approve") return own || railStatus({ lane: "blocked" });
  if (closed && own) return own;
  const st = railStatus(owed === false && owedNoDraft(rail) ? { ...rail, draft: true } : rail, cantSend, page) || own;
  if (owed && ["approve", UNSENDABLE].includes(st?.key) && rail?.kind !== "action") return said(OWED, KIND_META[OWED], false);
  return cantSend && st?.key === "approve" && rail?.kind !== "action" ? said(UNSENDABLE, KIND_META[UNSENDABLE], false) : st;
};

// what a row's icon says to a reader that cannot see it: the state's words (a screen reader, a hover, a reader without colour)
export const statusLabel = (st, agent = "") => (!st ? "" : st.spins ? `${agent || "an agent"} is working on this` : st.word);

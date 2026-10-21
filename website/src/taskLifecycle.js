import { closeoutOf } from "./reviewProposal.js";
import { WORD } from "./lanes.js";
// Task, agent and reply are deliberately separate state machines. Keep these labels pure so
// Tasks, Timeline and tests cannot quietly invent different meanings for the same record.
export const STAY_OPEN_TAG = "stay:open";

const tags = (value) => String(value || "").split(/[\s,]+/).filter(Boolean);

export const ownerControlsCompletion = (task) =>
  tags(task?.Tags ?? task?.TaskTags).includes(STAY_OPEN_TAG);

export const taskPhase = (status) => {
  const value = String(status || "open").toLowerCase();
  if (value === "in_progress") return "in progress";
  return value;
};

// ONE WORD PER AGENT STATE, the words lanes.json gives the rail (the owner, 2026-09-25: "let's unify
// the vocab for agent status ... show it everywhere").
export const AGENT = { waiting: WORD.blocked, working: WORD.working, saved: WORD.saved, stopped: WORD.stopped, finished: WORD.agentdone,
  idle: WORD.queued };

// `finished`: the agent closed the task itself (the server's state, taskstate.py) - its report is its result, never
// "stopped and saved" (T6). `handed`: false when no agent was ever given this task - it has no agent state at all, not
// "waiting to start" (T5).
// `state`: the server's word for the task (taskstate.py) - saved, stopped or waiting to start is what the list and the
// Board say, so the page says it too instead of guessing from the facts it happens to have loaded (2026-09-25 pass).
const FROM_STATE = { saved: AGENT.saved, stopped: AGENT.stopped, queued: AGENT.idle };
export const agentPhase = ({ session, run, transcript, report, conversation, finished, handed, state } = {}) => {
  if (session?.alive) return session.waiting ? AGENT.waiting : AGENT.working;
  if (run?.Status === "running") return AGENT.working;
  if (finished) return AGENT.finished;
  if (FROM_STATE[state]) return FROM_STATE[state];
  if (report) return AGENT.saved;
  if (transcript) return AGENT.stopped;
  // General work keeps its record in the conversation, not in a pty. Its provider session ends
  // with the answer, and the card then read as never started over a chat full of work (owner, 2026-09-07).
  if (conversation) return AGENT.saved;
  return handed === false ? null : AGENT.idle;
};

// WHAT A LIVE SESSION SAYS ABOUT ITSELF, as one comparable value: whether it is alive and waiting, its sub-state and sentence, the
// question an answer binds to. The task page holds the session it found and must take the same session's new word when it changes (G7).
export const sessionWord = (s) => (s ? JSON.stringify([!!s.alive, !!s.waiting, s.state || null, s.line || null, s.request?.request_id || null,
  (s.questions || []).length, !!s.held, !!s.promptPending, s.busy ?? null]) : "");

// A general agent's chat stays open after it answers, so "the session exists" is not "it is working": open and not busy is an
// answer waiting on you (the owner, 2026-10-15: the heading said "researcher is working" under its finished answer). A pty
// session has no `busy`, so a coding agent is never read this way.
export const generalAnswered = (isGeneral, session) => !!(isGeneral && session?.alive && session.busy === false);

// Action proposals (write a playbook, push a branch, close an issue) share the review table
// with outbound replies, but they are not communication. A proposal is normally queued after
// the reply, so blindly taking reviews[0] makes its JSON envelope appear as the current draft.
// ...nor are a task's emails (slots.py): their own block (SlotList), never the reply card
const isReply = (review) => review.Kind !== "action" && review.Kind !== "slot";
export const pendingReplyReview = (reviews = []) =>
  reviews.find((review) => isReply(review) && review.Status === "pending");
// what closes this task, said under the task bar: the reply, its emails (slots.py), or the triaged work itself
// `noSender`: a task the owner typed has nobody to answer, and its card said "sending the reply closes it" under
// "Nobody sent this one, so there is nobody to answer" - the one way out it named did not exist
export const completionLine = (manual, owesEmails, noSender = false) => !manual
  ? "Automatic task. When its work is done, Taskuary may close it and prepare the reply."
  : owesEmails ? "You control completion. Ending an agent run leaves this task open; it closes when its emails are sent or dropped."
  : noSender ? "You control completion. Ending an agent run leaves this task open; press Mark done when it's finished."
  : "You control completion. Ending an agent run leaves this task open, and so does sending the reply - Mark done closes it.";
// ...and the same answer as a FACT on the settings row, beside the pills it belongs with: the sentence above sat
// right-aligned across two lines and explained ("Hate the why. Just tell me what." - the owner); it is the tooltip now.
export const completionFact = (manual, owesEmails, noSender = false) => !manual ? "closes itself when the work is done"
  : owesEmails ? "closes when its emails are sent" : "closes when you mark it done";
export const slotReviews = (reviews = []) => (reviews || []).filter((review) => review.Kind === "slot");
// what one Approve all may send: drafted, addressed, and asked for - never an address the agent added on its own
export const bulkSendable = (items = [], reviews = []) => {
  const byRid = Object.fromEntries(slotReviews(reviews).map((r) => [r.ReviewId, r]));
  return items.filter((i) => i.out?.by !== "agent" && String(i.out?.to || "").includes("@")).map((i) => byRid[i.rid])
    .filter((r) => r?.Status === "pending" && String(r.DraftText || "").trim());
};
export const slotState = (item, rv) => item.done ? (rv && ["approved", "edited", "sent"].includes(rv.Status) ? "sent" : "dropped")
  : rv?.Status === "pending" ? "waits for your yes" : "to draft";

// ...and the one closed WITHOUT sending: the draft stays on the task whatever became of it, a done task
// included (the owner, 2026-09-24: "draft should always stay on task even on done task"). Newest wins.
// `superseded` included: closing the task sweeps a pending draft away under that word, and the merged pull request's
// thank-you vanished from Close out with it (2026-10-12)
export const unsentReplyReview = (reviews = []) =>
  [...reviews].sort((a, b) => (b.ReviewId || 0) - (a.ReviewId || 0)).find((review) => isReply(review) &&
    ["no_reply", "closed_unsent", "rejected", "superseded"].includes(review.Status) && String(review.DraftText || "").trim());

// what went out on this task from OUTSIDE a draft here - your reply in the mail client, your comment on the pull request,
// and an agent's under your login, which come back as your own messages (channels.ingest_own_message). Oldest first.
// ...never our own send come back: the mailbox's Sent copy of a reply approved here is that reply, not one "already sent" from
// somewhere else - it was drawn as a second letter over the approved one (2026-10-13). Matched on the words, spacing aside:
// the provider's copy re-wraps the signature and may carry the quoted thread after it.
const flat = (s) => String(s || "").toLowerCase().replace(/\s+/g, "");
export const sentElsewhere = (messages = [], reviews = []) => {
  const ours = (reviews || []).filter((r) => ["approved", "edited", "sent"].includes(r.Status))
    .map((r) => flat(r.FinalText || r.DraftText).slice(0, 200)).filter(Boolean);
  return (messages || []).filter((m) => {
    const body = flat(m.OwnText || m.BodyText);
    return m.Direction === "out" && !m.ReviewSent && body && !ours.some((o) => body.startsWith(o) || o.startsWith(body.slice(0, 200)));
  });
};

export const sentReplyReview = (reviews = []) =>
  reviews.find((review) => isReply(review) &&
    ["approved", "edited", "sent"].includes(review.Status));

// ...and the proposals themselves, which share the reply's stage rather than getting one of their
// own: lanes.json has ONE lane for both ("a reply or an action is drafted and waits for your yes"),
// and one lane on the rail must be one section on the page or the two surfaces disagree about how
// many things are happening. Oldest first - a proposal is queued after the reply it follows, and
// the reply stays on top because sending it is what settles the task.
export const pendingProposals = (reviews = []) =>
  (reviews || []).filter((review) => review.Kind === "action" && review.Status === "pending").reverse();

// A row Taskuary wrote itself - work you started here, a scheduled report, the assistant speaking -
// has no correspondent, so there is nobody a reply could go to. The same list as wrapup.no_one_behind,
// which is what stops a finished session drafting into the void; the buttons never asked, so "Write
// reply" on a task the owner typed himself drafted an answer TO HIM - the model's own analysis, with
// a letter suggested underneath it, in the box that sends (the owner, 2026-09-22, TQ-0674).
export const NO_ONE_BEHIND = ["", "own", "report", "assistant"];
export const hasCorrespondent = (m) => !!m && !NO_ONE_BEHIND.includes(String(m?.Channel || "").toLowerCase());
// WHAT A REPLY ANSWERS: the newest row that came in from SOMEBODY (wrapup.reply_target) - a report joined onto the task is newer
// than the colleague's mail and said "Nobody sent this one" over a task with a person waiting (2026-10-13); only a task with
// nobody behind any row falls back to its newest
export const replySource = (messages = []) => {
  const inbound = [...(messages || [])].reverse().filter((m) => m.Status !== "context" && m.Direction !== "out");
  return inbound.find(hasCorrespondent) || inbound[0];
};

// lanes.json's word for the approve lane - ONE word for a reply and a close-out alike (the owner, 2026-09-27: "it should
// the same everywhere"), because both are the step that closes the task
export const READY = WORD.approve;
// ...and a reply the server REFUSED is not ready to send: the chip read "reply · ready to send" in green over it (the UI audit, 2026-10-21)
export const NOT_SENT = WORD.not_sent;

export const replyPhase = (reviews = []) => {
  const replyReviews = reviews.filter((review) => review.Kind !== "action");
  const latest = replyReviews[0];
  const pending = pendingReplyReview(replyReviews);
  if (pending?.DeliveryState === "failed") return NOT_SENT;
  if (pending || reviews.some((r) => r.Status === "pending" && closeoutOf(r))) return READY;
  if (sentReplyReview(replyReviews)) return "sent";
  if (latest?.Status === "no_reply") return "not needed";
  return "not drafted";
};

// Three cards open at once never say which one is asking you for something. Exactly one stage is
// the focus and the other two fold to their heading: a pending draft outranks everything (sending
// it is the step that closes the task), then the agent, then the task itself.
//
// The agent stage earns the focus by having WORK IN IT, not by the task's kind. Kind alone opened it
// on every coding and general task, including the ones whose agent may never start: a Power BI alert
// from a no-reply address is the assistant's by kind, and the first-time-sender gate then forbids the
// start - so the page opened on an empty pane offering a button, with the ask itself folded away
// (the owner, 2026-09-14: "it should be the task (number 1 pane) ... why is the agent expanded?").
// A live session never reaches here at all; TasksView pins the agent stage while a pty is alive.
// the task's emails (slots.py) drafted and waiting for a yes
export const waitingEmails = (checklist = [], reviews = []) => {
  const pending = new Set(slotReviews(reviews).filter((r) => r.Status === "pending").map((r) => r.ReviewId));
  return (checklist || []).filter((i) => i.out && !i.done && pending.has(i.rid)).length;
};

// SOMETHING WENT OUT on the task's close-out: a reply sent, a pull request merged or an issue closed (an approved action), an email
// the task owed - each approved, edited or sent. focusStage keeps the page on Close out after any of them (the owner, 2026-10-19:
// "when you hit send email or close any other task by merging PR it keeps the close out section of the app open")
export const wentOut = (reviews = []) => (reviews || []).some((r) => ["approved", "edited", "sent"].includes(r.Status));

export const focusStage = ({ kind, task, agent, reply, hasSender, proposal, agentSub, emails = 0, news = false, record = false, out = false } = {}) => {
  if (reply === READY || reply === NOT_SENT) return "reply";
  // ONE EVENT SEEN TWICE. An agent parked because it PROPOSED something is not two things wanting
  // the page: approving the proposal is what releases it. Opening the agent stage there would show
  // a terminal at a prompt with the thing that unblocks it folded away one card below. Parked on
  // anything else - a question, a wall - the agent is what stopped, and it wins.
  // funnelPile.assistantFocus carries the same exception; the two are asserted against each other.
  if (proposal && agentSub === "approval") return "reply";
  if (agent === AGENT.waiting) return "agent";
  // ...and the emails the task owes, drafted and waiting for a yes (TQ-0957: four drafts folded away in stage 1)
  if (emails) return "reply";
  // a proposal is otherwise the same stage and the same kind of ask. It has no sender and it can
  // outlive the task being closed, so it is judged before either of those gates.
  if (proposal) return "reply";
  if (hasSender && kind === "reply" && !["sent", "not needed"].includes(reply)) return "reply";
  // A FINISHED TASK OPENS ON THE LAST THING DONE (the owner, 2026-10-15: "if finished show the last thing done so either
  // agent work, or message sent"): the reply that went out, else what the agent did, else the task itself. It opened on the
  // Task step for every closed task, so a task the agent finished and closed showed its checklist, not what it found.
  // ...and a task YOU closed opens on Close out, where Mark done was pressed, showing the close (the owner, 2026-10-19: "i hit mark
  // done on close out but agent work tab opened up again"); a task the agent finished and closed itself still opens on its work
  if (task === "done") return reply === "sent" || out || agent !== AGENT.finished ? "reply" : "agent";
  if (task === "dropped") return record || (agent && agent !== AGENT.idle) ? "agent" : "task";
  // a sender wrote AFTER the agent's last session: the message is the news, the session's record is history (2026-10-12)
  if (news) return "task";
  // WHAT WENT OUT STAYS ON SCREEN (the owner, 2026-10-19: "you hit send ... it goes back to the general agent?? The agent was
  // already closed"): Send - and a merge, a closed issue, an owed email (wentOut) - keeps the task open now (2026-10-18), and an open
  // task with an agent's record fell to the agent stage below -
  // the page jumped back to a finished agent's conversation. Close out holds what went out and the Mark done that is the move now;
  // only an agent working again (or one queued to start, shown on the task) takes the page.
  if ((reply === "sent" || out) && ![AGENT.working, AGENT.idle].includes(agent)) return "reply";
  if (agent && agent !== AGENT.idle) return "agent";
  return "task";
};

export const timelinePhases = (row) => ({
  task: taskPhase(row?.TaskStatus),
  agent: row?.AgentWaiting ? AGENT.waiting : row?.Working ? AGENT.working : null,
  reply: row?.ReviewStatus === "pending" ? (row?.HasDraft === 0 ? "needed" : "ready")
    : ["approved", "edited", "sent"].includes(row?.ReviewStatus) ? "sent" : null,
});

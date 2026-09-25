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
export const AGENT = { waiting: "agent waiting on you", working: "agent working", saved: "session saved",
  stopped: "agent stopped", finished: "agent finished", idle: "waiting to start" };

// `finished`: the agent closed the task itself (the server's state, taskstate.py) - its report is its result, never
// "session saved" (T6). `handed`: false when no agent was ever given this task - it has no agent state at all, not
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

// Action proposals (write a playbook, push a branch, close an issue) share the review table
// with outbound replies, but they are not communication. A proposal is normally queued after
// the reply, so blindly taking reviews[0] makes its JSON envelope appear as the current draft.
export const pendingReplyReview = (reviews = []) =>
  reviews.find((review) => review.Kind !== "action" && review.Status === "pending");

// ...and the one closed WITHOUT sending: the draft stays on the task whatever became of it, a done task
// included (the owner, 2026-09-24: "draft should always stay on task even on done task"). Newest wins.
export const unsentReplyReview = (reviews = []) =>
  [...reviews].sort((a, b) => (b.ReviewId || 0) - (a.ReviewId || 0)).find((review) => review.Kind !== "action" &&
    ["no_reply", "closed_unsent", "rejected"].includes(review.Status) && String(review.DraftText || "").trim());

export const sentReplyReview = (reviews = []) =>
  reviews.find((review) => review.Kind !== "action" &&
    ["approved", "edited", "sent"].includes(review.Status));

// ...and the proposals themselves, which share the reply's stage rather than getting one of their
// own: lanes.json has ONE lane for both ("a reply or an action is drafted and waits for your yes"),
// and one lane on the rail must be one section on the page or the two surfaces disagree about how
// many things are happening. Oldest first - a proposal is queued after the reply it follows, and
// the reply stays on top because sending it is what settles the task.
export const pendingProposals = (reviews = []) =>
  (reviews || []).filter((review) => review.Kind === "action" && review.Status === "pending").reverse();

// A row Taskuary wrote itself - work you started here, a scheduled report, the assistant speaking -
// has no correspondent, so there is nobody a reply could go to. The same list as coder.no_one_behind,
// which is what stops a finished session drafting into the void; the buttons never asked, so "Write
// reply" on a task the owner typed himself drafted an answer TO HIM - the model's own analysis, with
// a letter suggested underneath it, in the box that sends (the owner, 2026-09-22, TQ-0674).
export const NO_ONE_BEHIND = ["", "own", "report", "assistant"];
export const hasCorrespondent = (m) => !!m && !NO_ONE_BEHIND.includes(String(m?.Channel || "").toLowerCase());

export const replyPhase = (reviews = []) => {
  const replyReviews = reviews.filter((review) => review.Kind !== "action");
  const latest = replyReviews[0];
  if (pendingReplyReview(replyReviews)) return "reply ready";
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
export const focusStage = ({ kind, task, agent, reply, hasSender, proposal, agentSub } = {}) => {
  if (reply === "reply ready") return "reply";
  // ONE EVENT SEEN TWICE. An agent parked because it PROPOSED something is not two things wanting
  // the page: approving the proposal is what releases it. Opening the agent stage there would show
  // a terminal at a prompt with the thing that unblocks it folded away one card below. Parked on
  // anything else - a question, a wall - the agent is what stopped, and it wins.
  // funnelPile.assistantFocus carries the same exception; the two are asserted against each other.
  if (proposal && agentSub === "approval") return "reply";
  if (agent === AGENT.waiting) return "agent";
  // a proposal is otherwise the same stage and the same kind of ask. It has no sender and it can
  // outlive the task being closed, so it is judged before either of those gates.
  if (proposal) return "reply";
  if (hasSender && kind === "reply" && !["sent", "not needed"].includes(reply)) return "reply";
  if (["done", "dropped"].includes(task)) return "task";
  if (agent && agent !== AGENT.idle) return "agent";
  return "task";
};

export const timelinePhases = (row) => ({
  task: taskPhase(row?.TaskStatus),
  agent: row?.AgentWaiting ? AGENT.waiting : row?.Working ? AGENT.working : null,
  reply: row?.ReviewStatus === "pending" ? (row?.HasDraft === 0 ? "needed" : "ready")
    : ["approved", "edited", "sent"].includes(row?.ReviewStatus) ? "sent" : null,
});

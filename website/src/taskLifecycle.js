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

export const agentPhase = ({ session, run, transcript, report } = {}) => {
  if (session?.alive) return session.waiting ? "needs you" : "working";
  if (run?.Status === "running") return "working";
  if (report) return "result ready";
  if (transcript) return "stopped";
  return "not started";
};

// Action proposals (write a playbook, push a branch, close an issue) share the Review table
// with outbound replies, but they are not communication. A proposal is normally queued after
// the reply, so blindly taking reviews[0] makes its JSON envelope appear as the current draft.
export const pendingReplyReview = (reviews = []) =>
  reviews.find((review) => review.Kind !== "action" && review.Status === "pending");

export const sentReplyReview = (reviews = []) =>
  reviews.find((review) => review.Kind !== "action" &&
    ["approved", "edited", "sent"].includes(review.Status));

export const replyPhase = (reviews = []) => {
  const replyReviews = reviews.filter((review) => review.Kind !== "action");
  const latest = replyReviews[0];
  if (pendingReplyReview(replyReviews)) return "draft ready";
  if (sentReplyReview(replyReviews)) return "sent";
  if (latest?.Status === "no_reply") return "not needed";
  return "not drafted";
};

export const timelinePhases = (row) => ({
  task: taskPhase(row?.TaskStatus),
  agent: row?.AgentWaiting ? "needs you" : row?.Working ? "working" : null,
  reply: row?.ReviewStatus === "pending" ? (row?.HasDraft === 0 ? "needed" : "ready")
    : ["approved", "edited", "sent"].includes(row?.ReviewStatus) ? "sent" : null,
});

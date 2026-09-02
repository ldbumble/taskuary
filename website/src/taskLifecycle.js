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

export const replyPhase = (reviews = []) => {
  const latest = reviews[0];
  const pending = reviews.find((review) => review.Status === "pending");
  if (pending) return pending.Kind === "action" ? "approval needed" : "draft ready";
  if (latest && ["approved", "edited", "sent"].includes(latest.Status)) return "sent";
  if (latest?.Status === "no_reply") return "not needed";
  return "not drafted";
};

export const timelinePhases = (row) => ({
  task: taskPhase(row?.TaskStatus),
  agent: row?.AgentWaiting ? "needs you" : row?.Working ? "working" : null,
  reply: row?.ReviewStatus === "pending" ? (row?.HasDraft === 0 ? "needed" : "ready")
    : ["approved", "edited", "sent"].includes(row?.ReviewStatus) ? "sent" : null,
});

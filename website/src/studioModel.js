import { assignedAgent } from "./agentIdentity.js";

export const studioTaskIsLive = (task) => !!(task && (task.Session || task.RunStatus === "running"));

export function studioAgentName(task, liveRow, configuredAgents = []) {
  const named = liveRow?.AgentName || task?.Session?.agent || task?.RunAgent || assignedAgent(task?.Assignee);
  if (named) return named;
  return configuredAgents[0]?.Name || "agent";
}

export function studioPose(task) {
  if (!task) return "free";
  if (task.Status === "waiting" || task.ReviewStatus === "pending") return "hand";
  if (studioTaskIsLive(task)) return task.Kind === "coding" ? "type" : "paper";
  return "sit";
}

export function studioSeats(tasks = [], capacity = 4) {
  const count = Math.max(1, Math.min(8, Number(capacity) || 4));
  const live = tasks.filter(studioTaskIsLive);
  const waiting = tasks.filter((task) => !live.includes(task)
    && (task.Status === "waiting" || task.ReviewStatus === "pending"));
  const occupied = [...live, ...waiting].slice(0, count);
  return Array.from({ length: count }, (_, index) => occupied[index] || null);
}

export function studioElapsed(task, liveRow, now = Date.now()) {
  const at = liveRow?.StartedAt || task?.Session?.started || task?.RunStartedAt;
  if (!at) return "";
  const seconds = Math.max(0, (now - new Date(String(at).replace(" ", "T"))) / 1000);
  return seconds < 90 ? `${Math.round(seconds)}s`
    : seconds < 5400 ? `${Math.round(seconds / 60)}m`
      : `${(seconds / 3600).toFixed(1)}h`;
}

export function studioTaskState(task, liveRow, configuredAgents = [], now = Date.now()) {
  if (!task) return { agent: "", label: "free", tone: "free", pose: "free" };
  const agent = studioAgentName(task, liveRow, configuredAgents);
  if (task.Status === "waiting" || task.ReviewStatus === "pending") {
    return { agent, label: "waiting on you", tone: "waiting", pose: "hand" };
  }
  if (studioTaskIsLive(task)) {
    const elapsed = studioElapsed(task, liveRow, now);
    return { agent, label: elapsed ? `working · ${elapsed}` : "working", tone: "working", pose: studioPose(task) };
  }
  return { agent, label: "open", tone: "open", pose: "sit" };
}

import { shownAgent } from "./kinds.js";
import { durSince } from "./timeWords.js";

export const studioTaskIsLive = (task) => !!(task && (task.Session || task.RunStatus === "running"));
// WAITING IS THE BOARD'S RULE (B20): the game said "working · 21m" over agents the Board listed as waiting on you - a running session
// sitting at its prompt is waiting, not working. Same reading as ui.isWaiting (the server's verdict, else 45s of quiet) and the
// Board's blocked state; written here because node tests this file without the JSX
const asks = (s) => !!s && (s.waiting ?? (s.idle >= 45));
export const studioTaskWaits = (task, liveRow = null) => !!task && (task.Status === "waiting" || task.ReviewStatus === "pending" || task.State === "blocked"
  || (liveRow?.kind === "session" && asks(liveRow)) || (!!task.Session?.alive && asks(task.Session)));

// the desk's name tag: Taskuary, or the tool a coding session runs - never the profile it runs under (kinds.js shownAgent)
export function studioAgentName(task, liveRow) { return shownAgent(liveRow || task?.Session); }

export function studioPose(task) {
  if (!task) return "free";
  if (studioTaskWaits(task)) return "hand";
  if (studioTaskIsLive(task)) return task.Kind === "coding" ? "type" : "paper";
  return "sit";
}

export function studioSeats(tasks = [], capacity = 4) {
  const count = Math.max(1, Math.min(8, Number(capacity) || 4));
  const live = tasks.filter(studioTaskIsLive);
  const waiting = tasks.filter((task) => !live.includes(task) && studioTaskWaits(task));
  const occupied = [...live, ...waiting].slice(0, count);
  return Array.from({ length: count }, (_, index) => occupied[index] || null);
}

export function studioElapsed(task, liveRow, now = Date.now()) {
  const at = liveRow?.StartedAt || task?.Session?.started || task?.RunStartedAt;
  if (!at) return "";
  return durSince(at, now);
}

export function studioTaskState(task, liveRow, configuredAgents = [], now = Date.now()) {
  if (!task) return { agent: "", label: "free", tone: "free", pose: "free" };
  const agent = studioAgentName(task, liveRow, configuredAgents);
  if (studioTaskWaits(task, liveRow)) {
    return { agent, label: "waiting on you", tone: "waiting", pose: "hand" };
  }
  if (studioTaskIsLive(task)) {
    const elapsed = studioElapsed(task, liveRow, now);
    return { agent, label: elapsed ? `working · ${elapsed}` : "working", tone: "working", pose: studioPose(task) };
  }
  return { agent, label: "open", tone: "open", pose: "sit" };
}

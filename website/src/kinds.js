// WHO DOES A TASK, read from taskuary/kinds.json - the same file the server reads (taskuary/kinds.py). The task list's new-task
// dialog and the task page's picker each typed their own copy, with different hints; triage's panel and the agent step a third
// and fourth (the cleanup round, 2026-10-18). WHO works it, then what it is (the owner, 2026-09-10: "tag tasks as reply/your
// task/agent (maybe coding vs general)") - "your task" is the same phrase the work rail's own heading uses.
import kinds from "../../taskuary/kinds.json" with { type: "json" };

export const KIND_OPTIONS = kinds.kinds;
export const KINDS = KIND_OPTIONS.map((k) => k.key);
const KIND = Object.fromEntries(KIND_OPTIONS.map((k) => [k.key, k]));
export const AGENT_KINDS = KINDS.filter((k) => KIND[k].agent);
export const kindLabel = (kind) => KIND[kind]?.label || kind;
// the picker's name without "agent · " - the row's chip beside the agent's own name
export const shortKind = (kind) => String(kindLabel(kind || "task")).replace(/^agent · /, "");
// what triage's panel calls the destination ("Coding agent", "My task list")
export const verdictLabel = (kind) => KIND[kind]?.verdict || String(kind || "");
// "Start the coding agent": who works it, said by what it IS - a profile's name is not a worker (the owner, 2026-10-16)
export const agentWord = (kind) => KIND[kind === "coding" ? "coding" : "general"].worker;
// WHO THE OWNER SEES AT WORK (kinds.json `shown_`, the owner 2026-10-28): Taskuary, whatever profile the agent runs under. A coding
// session may name its tool (`cli`); a chat session's `cli` is Taskuary's own. The profile is told on hover only (instructionsHint).
export const AGENT_SHOWN = kinds.shown;
export const shownAgent = (run) => {
  const tool = ["chat", "assistant"].includes(String(run?.mode || "")) ? "" : String(run?.cli || "").trim();
  return tool && tool.toLowerCase() !== AGENT_SHOWN.toLowerCase() ? tool : AGENT_SHOWN;
};
export const instructionsHint = (profile) => profile ? `Instructions: ${profile}` : "";

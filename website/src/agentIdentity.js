import { AGENT_SHOWN } from "./kinds.js";

// A task stores people and bots in one Assignee field. `agent:` is storage syntax only, and the profile after it is the
// instructions the agent runs under, never who it is: screens say Taskuary (kinds.json `shown_`), never "agent:Atlas" or "Atlas"
// (the owner, 2026-10-29: hide profile names in Settings and the Assigned to picker too). The profile is told on hover only.
export const agentAssignee = (name) => name ? `agent:${name}` : "";

export const assignedAgent = (value) => {
  const text = String(value || "");
  return text.startsWith("agent:") ? text.slice(6) : "";
};

export const assigneeLabel = (value) => value === "owner"
  ? "you" : assignedAgent(value) ? AGENT_SHOWN : value || "unassigned";

// Who wrote a wall note: the page posts as "you", the server stamps its own actor "owner", and a note may carry the
// owner's own name - which the server sends with the notes (`owner`), never a name hardcoded here (2026-10-11).
export const isOwnerAuthor = (who, ownerName) => {
  const w = String(who || "").trim().toLowerCase();
  return !!w && (w === "you" || w === "owner" || w === String(ownerName || "").trim().toLowerCase());
};

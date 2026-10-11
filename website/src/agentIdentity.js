// A task stores people and bots in one Assignee field. `agent:` is storage syntax only;
// screens show the configured worker's stable name (Atlas), never "agent:Atlas".
export const agentAssignee = (name) => name ? `agent:${name}` : "";

export const assignedAgent = (value) => {
  const text = String(value || "");
  return text.startsWith("agent:") ? text.slice(6) : "";
};

export const assigneeLabel = (value) => value === "owner"
  ? "you" : assignedAgent(value) || value || "unassigned";

// Who wrote a wall note: the page posts as "you", the server stamps its own actor "owner", and a note may carry the
// owner's own name - which the server sends with the notes (`owner`), never a name hardcoded here (2026-10-11).
export const isOwnerAuthor = (who, ownerName) => {
  const w = String(who || "").trim().toLowerCase();
  return !!w && (w === "you" || w === "owner" || w === String(ownerName || "").trim().toLowerCase());
};

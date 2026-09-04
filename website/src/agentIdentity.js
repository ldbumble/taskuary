// A task stores people and bots in one Assignee field. `agent:` is storage syntax only;
// screens show the configured worker's stable name (Atlas), never "agent:Atlas".
export const agentAssignee = (name) => name ? `agent:${name}` : "";

export const assignedAgent = (value) => {
  const text = String(value || "");
  return text.startsWith("agent:") ? text.slice(6) : "";
};

export const assigneeLabel = (value) => value === "owner"
  ? "you" : assignedAgent(value) || value || "unassigned";

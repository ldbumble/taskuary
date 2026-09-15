const DISPLAY_KEYS = new Set([
  "intent", "kind", "profile", "playbook", "why", "title", "summary", "checklist",
  "repository", "needs_repo_choice", "repo_reason", "relationship", "related_message_ids",
  "existing_task_id", "notes", "notes_left",
]);

export const parseTriageVerdict = (route) => {
  const raw = route?.VerdictJson;
  if (!raw) return null;
  try {
    const value = typeof raw === "string" ? JSON.parse(raw) : raw;
    return value && typeof value === "object" && !Array.isArray(value) ? value : null;
  } catch {
    return null;
  }
};

export const latestTriageVerdict = (routes = []) => {
  for (let i = routes.length - 1; i >= 0; i -= 1) {
    const verdict = parseTriageVerdict(routes[i]);
    if (verdict) return verdict;
  }
  return null;
};

export const legacyTriageVerdict = ({ routeReason = "", routes = [], task = {}, checklist = [] } = {}) => {
  const savedRoute = [...routes].reverse()
    .find((route) => /^triage:\s*(task|reply_only|fyi)/i.test(String(route?.Reason || "")));
  const reason = String(savedRoute?.Reason || routeReason || "");
  const intent = (/^triage:\s*(task|reply_only|fyi)/i.exec(reason) || [])[1];
  if (!intent) return null;
  const repository = String(task?.Tags || "").split(",").map((value) => value.trim())
    .find((value) => value.toLowerCase().startsWith("repo:"));
  const items = checklist.map((value) => typeof value === "string" ? value : value?.text).filter(Boolean);
  const assignee = String(task?.Assignee || "");
  return {
    intent: intent.toLowerCase(),
    kind: task?.Kind || "",
    profile: assignee.startsWith("agent:") ? assignee.slice(6) : "",
    title: task?.Title || "",
    summary: task?.Summary || "",
    checklist: items,
    why: reason.replace(/^triage:\s*\w+\s*-\s*/, "").split(" · ")[0],
    repository: repository ? repository.slice(5) : "",
  };
};

export const intentLabel = (intent) => ({
  task: "Task",
  reply_only: "Reply needed",
  fyi: "FYI",
}[intent] || String(intent || "Unspecified"));

export const kindLabel = (kind) => ({
  coding: "Coding agent",
  general: "Assistant",
  task: "My task list",
  reply: "Reply review",
}[kind] || String(kind || ""));

export const relationshipLabel = (relationship) => ({
  new: "New item",
  continues: "Continues earlier work",
  answers: "Answers earlier work",
  uncertain: "Relationship uncertain",
}[relationship] || String(relationship || ""));

export const extraTriageFields = (verdict = {}) => Object.entries(verdict)
  .filter(([key, value]) => !DISPLAY_KEYS.has(key) && value !== null && value !== ""
    && (!Array.isArray(value) || value.length));

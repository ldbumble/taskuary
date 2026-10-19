// THE ROUTE RECORD LEADS WITH WHOSE IT IS (categories.route_head): "triage: work for the assistant - ...". Rows written
// before say "triage: task - ...", so the verdict is read in either wording - here, and nowhere else by regex.
const HEAD = /^triage:\s*(task|reply_only|fyi|yours to do|work for |needs a reply|nothing to do)/i;
const HEAD_INTENT = { "yours to do": "task", "work for ": "task", "needs a reply": "reply_only", "nothing to do": "fyi" };
export const routeIntent = (reason) => {
  const m = HEAD.exec(String(reason || ""));
  return m ? HEAD_INTENT[m[1].toLowerCase()] || m[1].toLowerCase() : "";
};
// triage's own reason, the head taken off: "triage: yours to do - she asks for X · ..." -> "she asks for X · ..."
export const routeWhy = (reason) => String(reason || "").replace(/^triage:\s*[^\u00b7]*?\s-\s/, "");

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
    .find((route) => routeIntent(route?.Reason));
  const reason = String(savedRoute?.Reason || routeReason || "");
  const intent = routeIntent(reason);
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
    why: routeWhy(reason).split(" · ")[0],
    repository: repository ? repository.slice(5) : "",
  };
};

export const intentLabel = (intent) => ({
  task: "Task",
  reply_only: "Reply needed",
  fyi: "FYI",
}[intent] || String(intent || "Unspecified"));

// what the panel calls each destination - kinds.json's `verdict`, the one table of task kinds
export { verdictLabel as kindLabel } from "./kinds.js";

export const relationshipLabel = (relationship) => ({
  new: "New item",
  continues: "Continues earlier work",
  answers: "Answers earlier work",
  uncertain: "Relationship uncertain",
}[relationship] || String(relationship || ""));

export const extraTriageFields = (verdict = {}) => Object.entries(verdict)
  .filter(([key, value]) => !DISPLAY_KEYS.has(key) && value !== null && value !== ""
    && (!Array.isArray(value) || value.length));

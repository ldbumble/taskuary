// WHAT THE AI USED ON THIS TASK (the owner, 2026-11-06: "show it on the task somewhere hidden you can open and see it"): each call and agent
// run, one line - when, the job, the model, quick/normal/hard, tokens and time - from GET /api/tasks/{id}/ai-used (aiusage.for_task).
// Uncounted is said by saying nothing, never 0.
export const tokens = (n) => n == null ? "" : n >= 1e6 ? `${(n / 1e6).toFixed(1).replace(/\.0$/, "")}M` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : String(n);
export const took = (s) => s == null ? "" : s < 1 ? "<1s" : s < 60 ? `${Math.round(s)}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`;
const tierWord = (t) => (t && t !== "as set" && t !== "held" ? t : "");
export const usedLine = (r) => [r.what, r.model, tierWord(r.tier), r.tokens != null ? `${tokens(r.tokens)} tokens` : "", took(r.seconds),
  r.calls > 1 ? `${r.calls} calls` : ""].filter(Boolean).join(" · ");
export const usedTotal = (t) => !t?.calls ? "" : [`${t.calls} ${t.calls === 1 ? "call" : "calls"}`, t.tokens != null ? `${tokens(t.tokens)} tokens` : "",
  took(t.seconds)].filter(Boolean).join(" · ");

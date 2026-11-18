// WHAT THE AI USED ON THIS TASK (the owner, 2026-11-06: "show it on the task somewhere hidden you can open and see it"): each call and agent
// run, one line - when, the job, the model, quick/normal/hard, tokens and time - from GET /api/tasks/{id}/ai-used (aiusage.for_task).
// Uncounted is said by saying nothing, never 0.
export const tokens = (n) => n == null ? "" : n >= 1e6 ? `${(n / 1e6).toFixed(1).replace(/\.0$/, "")}M` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : String(n);
export const took = (s) => s == null ? "" : s < 1 ? "<1s" : s < 60 ? `${Math.round(s)}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`;
// `tokens` are the new ones; what the provider's cache read back (an agent re-sends its whole conversation every step) is said apart
const tierWord = (t) => (t && t !== "as set" && t !== "held" ? t : "");
const counted = (o) => [o.tokens != null ? `${tokens(o.tokens)} tokens` : "", o.cached ? `${tokens(o.cached)} cached` : ""];
export const usedLine = (r) => [r.what, r.model, tierWord(r.tier), ...counted(r), took(r.seconds),
  r.calls > 1 ? `${r.calls} calls` : "", r.fell_back || ""].filter(Boolean).join(" · ");
export const usedTotal = (t) => !t?.calls ? "" : [`${t.calls} ${t.calls === 1 ? "call" : "calls"}`, ...counted(t), took(t.seconds)].filter(Boolean).join(" · ");

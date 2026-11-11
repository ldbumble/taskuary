// ONE STREAM, ONE MAPPER (the owner, 2026-11-06: "one shared chat object for coding and regular ... combine the code as much as possible").
// Every task's agent draws in the one chat (GeneralWorkspace.jsx), and every source it reads becomes ONE row shape here:
// - a general agent's run trace (general.shown_history's messages, the session's live `trace`) - trace events as agents.py writes them;
// - a turn of the task's one list (conversation.items): its steps in the log's shape ({k, text, name, args, file, edit, at} - a CLI's own log
//   as sessionrecord reads it, an ACP session's updates as conversation.acp_steps does), read into trace events (eventsOf).
// Trace events are the one currency: turnParts reads them into a turn's parts - its words, its work (agentSteps.stepsOf, one line a step),
// each edit its own row with its diff ("Edited budget.py (+12 −3)"), its plan a checklist. Whatever drew them, a turn is those parts.
import { baseName, describeCall, isWork, stepsOf } from "./agentSteps.js";
import { editHunks, stat } from "./diffView.js";
import { liveTerminal } from "./taskLayout.js";
import { filesOf, viewOf } from "./viewSpec.js";

// ── a coding session's steps -> trace events, the one currency ───────────────────────────────────
// a step the record kept without its arguments (saved before they were) is read off its one line of text
const argsOf = (s) => (s.args && Object.keys(s.args).length ? s.args
  : { file_path: s.file || s.text, command: s.detail || s.text, ...(s.detail ? { description: s.text } : {}), pattern: s.text, query: s.text, url: s.text });
// ...a call over ACP is running until ACP says it ran (`status`); a log's, until something came after it. A turn that is over has nothing running
const OVER = ["completed", "failed"];
const runs = (s, running, last) => running && (s.status ? !OVER.includes(s.status) : last);
// ...and one ACP still called pending or running when nothing runs any more NEVER FINISHED - a permission left open when Taskuary restarted, a
// session that died mid-call: drawn done, "Edited totals.py" read as made (the stress round, 2026-11-10)
const ended = (s, output) => (s.status && !OVER.includes(s.status) ? { result: output || "It never finished.", is_error: true }
  : { result: output, is_error: s.status === "failed" });
export const eventsOf = (steps, running, tail = true) => steps.flatMap((s, i) => {
  const id = s.id || `t${i}`, output = String(s.output || "").trim();
  if (s.k === "tool") return [{ type: "tool_call", name: s.name, detail: { tool_call_id: id, args: argsOf(s), output,
      ...(s.parent ? { parent: s.parent } : {}), ...(s.edit ? { edit: s.edit } : {}), ...(s.file ? { file: s.file } : {}) } },
    ...(runs(s, running, tail && i === steps.length - 1) ? [] : [{ type: "tool_result", name: id, detail: { tool_call_id: id, ...ended(s, output) } }])];
  if (s.k === "plan") return [{ type: "tool_call", name: "TodoWrite", detail: { tool_call_id: id, args: { todos: s.items || [] } } },
    { type: "tool_result", name: id, detail: { tool_call_id: id, result: "" } }];
  if (s.k === "said") return [{ type: "progress", name: "text", detail: s.text }];
  if (s.k === "thought") return [{ type: "progress", name: "thinking", detail: s.text }];
  if (s.k === "error") return [{ type: "error", detail: { result: s.text } }];
  return s.text ? [{ type: "progress", name: "note", detail: s.text }] : [];
});

// ── a tool call that is an EDIT, and one that is a PLAN ─────────────────────────────────────────
// AN EDIT IS ITS OWN ROW, its diff behind it: what the call carries - a log's own record of it (`edit`), else the before/after the tool was
// handed (Claude's old_string/new_string, a MultiEdit's edits, a Write's content, a patch) - so a general agent editing in a checkout gets them too
const FILE_KEYS = ["file_path", "path", "filePath", "absolute_path"];
const argEdit = (name, a) => {
  if (Array.isArray(a.edits) && a.edits.length) return { parts: a.edits.map((x) => ({ old: String(x?.old_string ?? ""), new: String(x?.new_string ?? "") })) };
  if (a.old_string != null || a.new_string != null) return { parts: [{ old: String(a.old_string ?? ""), new: String(a.new_string ?? "") }] };
  if (typeof a.content === "string" && /write|create/i.test(String(name || ""))) return { whole: true, parts: [{ old: "", new: a.content }] };
  if (typeof a.patch === "string" || typeof a.input === "string" && /\*\*\* (Update|Add) File|^@@/m.test(a.input)) return { patch: a.patch ?? a.input };
  return null;
};
// ...but an edit that FAILED or never ran is no edit made: drawn "Edited totals.py (+1 −1)" from the diff it asked to make, it read as done -
// it is its step, drawn failed (the stress round, 2026-11-10)
export function editOf(e, res) {
  if (e?.type !== "tool_call" || res?.detail?.is_error) return null;
  const d = e.detail || {}, a = d.args || {};
  if (!d.edit && describeCall(e.name, a).kind !== "edit") return null;
  const edit = d.edit || argEdit(e.name, a), file = d.file || FILE_KEYS.map((k) => a[k]).find(Boolean) || "";
  // ...a log's own edit row stands even with no diff kept; a trace's call is a row of its own only when it carries one
  return edit || d.file ? editRow({ name: e.name, edit, file }) : null;
}
export const editRow = (s) => {
  const hunks = editHunks(s.edit), { plus, minus } = stat(hunks), file = s.file || "";
  const wrote = /^(write|writefile|createfile)$/i.test(String(s.name || "").replace(/[^a-z]/gi, "")) || (hunks.length && hunks.every((h) => h.lines.every((l) => l[0] === "+")));
  return { type: "edit", file, summary: `${wrote ? "Wrote" : "Edited"} ${baseName(file) || "a file"}${hunks.length ? ` (+${plus} −${minus})` : ""}`, plus, minus, hunks };
};
// THE PLAN IS A CHECKLIST, the newest one of the turn where it was last updated - never "Updated its plan (3 steps)" six times over
const PLAN_MARK = { completed: "done", done: "done", in_progress: "now", now: "now" };
const PLAN_TOOLS = new Set(["todowrite", "updateplan", "update_plan"]);
export function planOf(e) {
  if (e?.type !== "tool_call" || !PLAN_TOOLS.has(String(e.name || "").toLowerCase().replace(/[^a-z_]/g, ""))) return null;
  const a = e.detail?.args || {}, list = a.todos || a.plan || [];
  const items = (Array.isArray(list) ? list : []).map((x) => (typeof x === "string" ? { text: x, status: "pending" } : { text: String(x?.text || x?.content || x?.step || ""), status: x?.status }))
    .filter((x) => x.text).map((x) => ({ text: x.text, state: PLAN_MARK[x.status] || "todo" }));
  return items.length ? { type: "plan", items } : null;
}

// ── THE ONE MAPPER: trace events -> a turn's parts ──────────────────────────────────────────────
// in order: its words, a fold of the work it did, each edit with its diff, each view it showed, its plan. `answer`: the words the turn
// filed as its answer, which its trail does not say twice (agentSteps.stepsOf). A call's result is its own wherever it came - a run of steps cut by an edit keeps the results
// that arrived after the edit, so nothing it started is left spinning
export function turnParts(events, { answer = "", keepStart = false } = {}) {
  const evs = (events || []).filter(Boolean), results = new Map(), parts = [], special = new Set();
  for (const e of evs) if (e.type === "tool_result") results.set(e.detail?.tool_call_id || e.name, e);
  let run = [], first = true;
  const flush = () => {
    if (!run.length) return;
    const ids = new Set(run.filter((e) => e.type === "tool_call").map((e) => e.detail?.tool_call_id));
    const got = [...ids].map((id) => results.get(id)).filter(Boolean);
    for (const st of stepsOf([...run, ...got], { answer, keepStart: keepStart && first })) {
      if (st.kind === "said") parts.push({ type: "said", text: st.summary });
      else { const w = parts.at(-1)?.type === "work" ? parts.at(-1) : (parts.push({ type: "work", steps: [] }), parts.at(-1)); w.steps.push(st); }
    }
    run = []; first = false;
  };
  for (const e of evs) {
    if (e.type === "tool_result") continue;
    // ...and a VIEW the agent showed (agenttools `show`) is its own part, drawn as the UI it describes (ViewSpec.jsx)
    // ...and the FILES it showed with it (viewSpec.filesOf): the pictures themselves, over any view the same call drew
    const res = results.get(e.detail?.tool_call_id), ps = [filesOf(e, res), editOf(e, res) || planOf(e) || viewOf(e, res)].filter(Boolean);
    if (ps.length) { flush(); special.add(e.detail?.tool_call_id); parts.push(...ps); } else run.push(e);
  }
  flush();
  // ...an edit that failed and was then made is no failure (agentSteps' `recovered`): Claude's first try at a string not found, its second made
  parts.forEach((p, i) => p.type === "work" && p.steps.forEach((s) => { if (s.status === "error" && s.kind === "edit"
    && parts.slice(i + 1).some((q) => q.type === "edit" && q.summary.startsWith(s.summary))) s.status = "recovered"; }));
  const lastPlan = parts.map((p) => p.type).lastIndexOf("plan");
  return parts.filter((p, i) => p.type !== "plan" || i === lastPlan).map((p, i) => ({ ...p, id: `p${i}` }));
}
// what a turn did, counted for its fold's line: "6 steps" - its edits each one
export const workCount = (parts) => (parts || []).reduce((n, p) => n + (p.type === "edit" ? 1 : p.type === "work" ? p.steps.filter(isWork).length : 0), 0);
export const hasParts = (parts) => (parts || []).some((p) => p.type !== "said" || p.text);

export const PARTS = "agent_parts";
export const partsMessage = (parts) => (parts.length ? [{ type: "data", name: PARTS, data: { parts } }] : []);
// WHICH SOURCE a task's chat reads: a coding task, or any task with a coding CLI live on it, is its sessions (codingchat.py); every other is
// the general agent's conversation (general.py). The one component draws either - this picks, nothing in the page does
export const chatSource = (task, term) => (task?.Kind === "coding" || liveTerminal(term) ? "coding" : "general");

// ── WHAT MAY DRAW AS AN INPUT (the owner, 2026-11-09: "inputs are messages in the prompt box or from the input channel - either the user
// themselves or someone else responds on the thread"): a bubble is what the owner TYPED, or what came in on the task's THREAD (a mail, a
// teammate's line, the owner's own reply from their phone). A press, an approval, a send, Taskuary's note to the agent, a wake, a fold, a
// check-back, an error - each is an event line or its card's result, never a bubble ──
// a FOLD is an input too: another task's work merged in is new work arriving on this one (the owner, 2026-11-09: "merging in a task is a new input of course")
export const INPUT_ORIGINS = ["typed", "thread", "fold"];
export const originOf = (m) => (m?.role !== "user" ? "agent" : (m.press || m.metadata?.custom?.press) ? "press"
  : (m.fold || m.metadata?.custom?.fold) ? "fold" : (m.mail?.length || m.metadata?.custom?.mail?.length) ? "thread"
  : (m.brief || m.metadata?.custom?.brief) ? "taskuary" : "typed");
export const isInput = (m) => INPUT_ORIGINS.includes(originOf(m));
// what TASKUARY's own short line that woke a turn says, as an event line ('' for its long instructions, which are never drawn)
export const eventOf = (words, fold = "", mail = []) => { const due = checkBackDue(words);
  return fold ? "" : due ? `Check-back due: ${due}` : !mail?.length && words && words.length <= 140 ? words : ""; };
export const linkWords = (u) => { const m = /github\.com\/[^/]+\/[^/]+\/(pull|issues)\/(\d+)/.exec(u); return m ? `${m[1] === "pull" ? "PR" : "issue"} #${m[2]}` : u.replace(/^https?:\/\//, "").slice(0, 60); };
export const checkBackDue = (w) => (/^TASKUARY: the check-back you set on this task is due - ([\s\S]*?)\. Check it now/.exec(String(w || "").trim()) || [])[1] || "";
// ...and in the general chat a turn after a press is the same turn going on: no new head, unless an input came between (isInput)
export const continues = (messages, i) => { for (let j = i - 1; j >= 0; j--) { const m = messages[j];
  if (m?.role === "assistant") return true; if (isInput(m)) return false; } return false; };

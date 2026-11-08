// ONE STREAM, ONE MAPPER (the owner, 2026-11-06: "one shared chat object for coding and regular ... combine the code as much as possible").
// Every task's agent draws in the one chat (GeneralWorkspace.jsx), and every source it reads becomes ONE row shape here:
// - a general agent's run trace (general.shown_history's messages, the session's live `trace`) - trace events as agents.py writes them;
// - a coding session (codingchat.py): the CLI's own log read into steps (sessionrecord: {k, text, name, args, file, edit, at}), or, run over
//   ACP, its session/update notifications (codingchat.record_update) - read into the log's steps (stepsFromAcp), then into trace events (eventsOf).
// Trace events are the one currency: turnParts reads them into a turn's parts - its words, its work (agentSteps.stepsOf, one line a step),
// each edit its own row with its diff ("Edited budget.py (+12 −3)"), its plan a checklist. Whatever drew them, a turn is those parts.
import { baseName, describeCall, isWork, stepsOf } from "./agentSteps.js";
import { editHunks, stat } from "./diffView.js";
import { liveTerminal } from "./taskLayout.js";
import { viewOf } from "./viewSpec.js";

// ── ACP's session/update -> the log's step shape ─────────────────────────────────────────────────
// an ACP tool call names its KIND (read, edit, execute...), not a tool: the name a log would carry for it, so describeCall reads both alike
const ACP_TOOL = { read: "Read", edit: "Edit", delete: "Delete", move: "Move", search: "Grep", execute: "Bash", fetch: "WebFetch", think: "Think" };
const textOf = (c) => (typeof c === "string" ? c : Array.isArray(c) ? c.map(textOf).join("") : c?.type === "text" ? c.text || "" : c?.content ? textOf(c.content) : "");
const ARGS = ["command", "cmd", "pattern", "query", "url", "file_path", "path", "filePath", "absolute_path", "description", "prompt", "glob", "title", "subagent_type"];
const small = (o) => Object.fromEntries(Object.entries(o || {}).filter(([k, v]) => ARGS.includes(k) && typeof v === "string" && v.trim()));
// A COMMAND'S OUTPUT IS ITS OWN STEP'S (the owner, 2026-11-06: "hate this terminal button. it's also not a terminal"): opened under its row, as
// an edit's diff is - Codex streams it (`terminal_output_delta`), Claude hands it with the result, fenced (acpcoding._unfence)
const unfence = (s) => String(s || "").replace(/^\s*```[\w-]*\n([^]*?)\n?```\s*$/, "$1");
const outOf = (u) => (u.content || []).filter((c) => c?.type === "content").map((c) => unfence(textOf(c.content))).join("\n")
  || (typeof u.rawOutput === "string" ? u.rawOutput : u.rawOutput?.formatted_output || u.rawOutput?.output || u.rawOutput?.stdout || "");
// ...and the helper call it runs under, when the adapter says (claude-code-acp's _meta.claudeCode.parentToolUseId; agents.parent_of)
export const parentOf = (u) => String(u?._meta?.claudeCode?.parentToolUseId || u?._meta?.parentToolUseId || u?._meta?.parentToolCallId || "");
export function stepsFromAcp(updates) {
  const out = [], byId = new Map();
  let o;
  // ...the agent's words arrive a token at a time: one step per run of chunks, as a log has one per block. A prompt Taskuary sent marks itself
  // its brief (`_meta.taskuary`), as mark_briefs marks a log's
  // ...each step at the moment its first update came in (`_at`, stamped as it was kept): ACP itself carries no time
  let at = "";
  const chunk = (k, t) => { if (!t) return; const last = out.at(-1); if (last?.k === k && last.open) last.text += t; else out.push({ k, text: t, open: true, ...(at ? { at } : {}) }); };
  for (const u of updates || []) {
    const kind = u?.sessionUpdate;
    at = u?._at || "";
    if (kind === "user_message_chunk") chunk(u._meta?.taskuary === "brief" ? "brief" : "you", textOf(u.content));
    else if (kind === "agent_message_chunk") chunk("said", textOf(u.content));
    else if (kind === "agent_thought_chunk") chunk("thought", textOf(u.content));
    else if (kind === "plan") out.push({ k: "plan", items: (u.entries || []).map((e) => ({ text: String(e?.content || ""), status: e?.status || "pending" })), ...(at ? { at } : {}) });
    else if (kind === "tool_call" || kind === "tool_call_update") {
      let s = byId.get(u.toolCallId);
      if (!s) {
        if (kind === "tool_call_update" && !u.rawInput && !u.title && !u.kind) continue;
        const tool = u._meta?.claudeCode?.toolName;
        s = { k: "tool", id: String(u.toolCallId || ""), name: tool || ACP_TOOL[u.kind] || u.title || u.kind || "tool", args: {}, ...(at ? { at } : {}) };
        byId.set(u.toolCallId, s); out.push(s);
      }
      const par = parentOf(u);
      if (par) s.parent = par;
      if (u.rawInput && typeof u.rawInput === "object") s.args = { ...s.args, ...small(u.rawInput) };
      // ...and where it is: running, done or failed, as ACP says - a call still running is drawn running, whatever came after it
      if (u.status) s.status = u.status;
      const d = u._meta?.terminal_output_delta?.data;
      if (d) s.out = (s.out || "") + d;
      else if (!s.out && (u.status === "completed" || u.status === "failed") && (o = outOf(u))) s.output = o;
      const loc = (u.locations || []).find((l) => l?.path)?.path;
      if (loc && !["path", "file_path", "filePath", "absolute_path"].some((k) => s.args[k])) s.args.file_path = loc;      // the key a log names a file by
      const diffs = (u.content || []).filter((c) => c?.type === "diff");
      if (diffs.length) { s.edit = { whole: true, parts: diffs.map((d) => ({ old: d.oldText || "", new: d.newText || "" })) }; s.file = diffs[0].path || loc || ""; }
      else if (loc && ["Edit", "Delete", "Move"].includes(s.name)) s.file = loc;
    }
  }
  return out.map(({ open, out: streamed, ...s }) => (s.text != null && s.k !== "tool" ? { ...s, text: s.text.trim() }
    : streamed ? { ...s, output: streamed } : s)).filter((s) => s.k === "tool" || s.k === "plan" || s.text);
}

// ── a coding session's steps -> trace events, the one currency ───────────────────────────────────
// a step the record kept without its arguments (saved before they were) is read off its one line of text
const argsOf = (s) => (s.args && Object.keys(s.args).length ? s.args
  : { file_path: s.file || s.text, command: s.detail || s.text, ...(s.detail ? { description: s.text } : {}), pattern: s.text, query: s.text, url: s.text });
// ...a call over ACP is running until ACP says it ran (`status`); a log's, until something came after it. A turn that is over has nothing running
const OVER = ["completed", "failed"];
const runs = (s, running, last) => running && (s.status ? !OVER.includes(s.status) : last);
export const eventsOf = (steps, running, tail = true) => steps.flatMap((s, i) => {
  const id = s.id || `t${i}`, output = String(s.output || "").trim();
  if (s.k === "tool") return [{ type: "tool_call", name: s.name, detail: { tool_call_id: id, args: argsOf(s), output,
      ...(s.parent ? { parent: s.parent } : {}), ...(s.edit ? { edit: s.edit } : {}), ...(s.file ? { file: s.file } : {}) } },
    ...(runs(s, running, tail && i === steps.length - 1) ? [] : [{ type: "tool_result", name: id, detail: { tool_call_id: id, result: output, is_error: s.status === "failed" } }])];
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
export function editOf(e) {
  if (e?.type !== "tool_call") return null;
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
    const p = editOf(e) || planOf(e) || viewOf(e, results.get(e.detail?.tool_call_id));
    if (p) { flush(); special.add(e.detail?.tool_call_id); parts.push(p); } else run.push(e);
  }
  flush();
  const lastPlan = parts.map((p) => p.type).lastIndexOf("plan");
  return parts.filter((p, i) => p.type !== "plan" || i === lastPlan).map((p, i) => ({ ...p, id: `p${i}` }));
}
// what a turn did, counted for its fold's line: "6 steps" - its edits each one
export const workCount = (parts) => (parts || []).reduce((n, p) => n + (p.type === "edit" ? 1 : p.type === "work" ? p.steps.filter(isWork).length : 0), 0);
export const hasParts = (parts) => (parts || []).some((p) => p.type !== "said" || p.text);

// ── a coding session -> the chat's rows: what came in, what the owner said, and each turn - oldest first ──
const at = (x) => String(x || "").replace("T", " ").slice(0, 19);
// THE OWNER'S WORDS INSIDE TASKUARY'S BRIEF (the owner, 2026-11-08: "i asked another question and the text was never sent into the prompt"): a line
// typed to a session at rest picks it back up (server continue-work) as "FROM THE OWNER: <words>" ahead of Resume's instructions - one brief, and
// the chat draws no brief, so their question stood nowhere. Their words are their line; the rest stays Taskuary's
export const ownerIn = (text) => (/^FROM THE OWNER:[ \t]*([^\n]+(?:\n(?!\n)[^\n]*)*)/.exec(String(text || "")) || [])[1]?.trim() || "";

export function chatRows({ sessions = [], mails = [], live = null, permissions = [] } = {}) {
  // THE TURN THAT ENDED IS NOT WORKING (the owner's live coding task, 2026-11-06: the turn ended on "Should I go ahead?", the chip said "agent
  // waiting on you", and "Working on this…" still turned under the answer): a live session is one that is alive, not one at work - it works
  // while the server says so (codingchat.live_of `working`), and a question on screen or a permission card is the owner's turn
  const working = (live ? live.working !== false : true), waiting = !!live?.asking || !!permissions?.length;
  const rows = [];
  sessions.forEach((ses, si) => {
    const steps = (ses.source === "acp" ? stepsFromAcp(ses.updates) : ses.steps || []).map((s) => ({ ...s, at: at(s.at) || at(ses.at) }));
    const now = !!ses.live && si === sessions.length - 1 && working;
    let turn = null;
    const close = () => { if (turn) rows.push(turn); turn = null; };
    steps.forEach((s) => {
      if (s.k === "you" || s.k === "brief") {
        close(); const w = s.k === "you" ? s.text : ownerIn(s.text);
        if (w) rows.push({ kind: "you", at: s.at, text: w });
        return;
      }
      if (s.k === "gap" || s.k === "screen") return;
      if (!turn) turn = { kind: "turn", at: s.at, sid: ses.sid, steps: [] };
      turn.steps.push(s);
    });
    close();
    // ...its newest turn is the one at work while its CLI runs
    const last = rows.at(-1);
    if (now && last?.kind === "turn" && last.sid === ses.sid) last.running = true;
  });
  // ...each mail where it came in: over the first entry at or after it, a run of them one row (the general chat's Arrived)
  const out = [], pending = [...mails].sort((a, b) => at(a.joined || a.at).localeCompare(at(b.joined || b.at)));
  const take = (upto) => { const got = []; while (pending.length && (upto == null || at(pending[0].joined || pending[0].at) <= upto)) got.push(pending.shift()); if (got.length) out.push({ kind: "mail", at: at(got.at(-1).at), mail: got }); };
  for (const r of rows) { if (r.at) take(r.at); out.push(r); }
  take(null);
  return out.map((r, i) => (r.kind === "turn"
    ? { kind: "turn", id: `r${i}`, at: r.at, running: !!r.running, waiting: !!r.running && waiting, parts: turnParts(eventsOf(r.steps, !!r.running)), answer: lastSaid(r.steps) }
    : { ...r, id: `r${i}` }));
}
const lastSaid = (steps) => [...steps].reverse().find((s) => s.k === "said")?.text || "";

// ...and those rows as the one thread's messages (GeneralWorkspace's AssistantThread): a mail is Taskuary's brief carrying it (drawn as what
// came in, on the right), the owner's line theirs, a turn the agent's - its parts the same data part a general turn carries. A turn at work
// is the live one (`live-…`), as the general chat's own live turn is
export const PARTS = "agent_parts";
export const partsMessage = (parts) => (parts.length ? [{ type: "data", name: PARTS, data: { parts } }] : []);
export const rowMessages = (rows, sid = "coding") => (rows || []).map((r) => (r.kind === "mail"
  ? { id: `${sid}-${r.id}`, role: "user", brief: true, mail: r.mail, content: [{ type: "text", text: r.mail.map((m) => m.words).join("\n") || " " }], createdAt: r.at }
  : r.kind === "you" ? { id: `${sid}-${r.id}`, role: "user", content: [{ type: "text", text: r.text }], createdAt: r.at }
  : { id: `${r.running ? "live-" : ""}${sid}-${r.id}`, role: "assistant", content: partsMessage(r.parts), createdAt: r.at, ...(r.waiting ? { waiting: true } : {}) }));

// WHICH SOURCE a task's chat reads: a coding task, or any task with a coding CLI live on it, is its sessions (codingchat.py); every other is
// the general agent's conversation (general.py). The one component draws either - this picks, nothing in the page does
export const chatSource = (task, term) => (task?.Kind === "coding" || liveTerminal(term) ? "coding" : "general");

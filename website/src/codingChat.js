// A CODING TASK IS THE SAME ONE CHAT (the owner, 2026-11-06: "combine the close out action in the coding cli as well. basically making general and
// coding agent more similar"). The server hands each session as the CLI's own log read into steps (sessionrecord: {k, text, name, args, file,
// edit, at}) or, run over ACP, as its session/update notifications (codingchat.record_update). Both become ONE row shape here: the ACP updates
// are read into the log's own steps first (stepsFromAcp), and every step line is the general chat's (agentSteps.describeCall / stepsOf) -
// "Read store.py", "Ran pytest", and an edit its own row with its diff, "Edited budget.py (+12 −3)".
import { baseName, describeCall, isWork, stepsOf } from "./agentSteps.js";
import { editHunks, stat } from "./diffView.js";

// ── ACP's session/update -> the log's step shape ─────────────────────────────────────────────────
// an ACP tool call names its KIND (read, edit, execute...), not a tool: the name a log would carry for it, so describeCall reads both alike
const ACP_TOOL = { read: "Read", edit: "Edit", delete: "Delete", move: "Move", search: "Grep", execute: "Bash", fetch: "WebFetch", think: "Think" };
const textOf = (c) => (typeof c === "string" ? c : Array.isArray(c) ? c.map(textOf).join("") : c?.type === "text" ? c.text || "" : c?.content ? textOf(c.content) : "");
const ARGS = ["command", "cmd", "pattern", "query", "url", "file_path", "path", "filePath", "absolute_path", "description", "prompt", "glob", "title"];
const small = (o) => Object.fromEntries(Object.entries(o || {}).filter(([k, v]) => ARGS.includes(k) && typeof v === "string" && v.trim()));
export function stepsFromAcp(updates) {
  const out = [], byId = new Map();
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
        s = { k: "tool", name: ACP_TOOL[u.kind] || u.title || u.kind || "tool", args: {}, ...(at ? { at } : {}) };
        byId.set(u.toolCallId, s); out.push(s);
      }
      if (u.rawInput && typeof u.rawInput === "object") s.args = { ...s.args, ...small(u.rawInput) };
      const loc = (u.locations || []).find((l) => l?.path)?.path;
      if (loc && !["path", "file_path", "filePath", "absolute_path"].some((k) => s.args[k])) s.args.file_path = loc;      // the key a log names a file by
      const diffs = (u.content || []).filter((c) => c?.type === "diff");
      if (diffs.length) { s.edit = { whole: true, parts: diffs.map((d) => ({ old: d.oldText || "", new: d.newText || "" })) }; s.file = diffs[0].path || loc || ""; }
      else if (loc && ["Edit", "Delete", "Move"].includes(s.name)) s.file = loc;
    }
  }
  return out.map(({ open, ...s }) => (s.text != null && s.k !== "tool" ? { ...s, text: s.text.trim() } : s)).filter((s) => s.k === "tool" || s.k === "plan" || s.text);
}

// ── one session's steps -> the trace events stepsOf reads ────────────────────────────────────────
// a step the record kept without its arguments (saved before they were) is read off its one line of text
const argsOf = (s) => (s.args && Object.keys(s.args).length ? s.args
  : { file_path: s.file || s.text, command: s.detail || s.text, ...(s.detail ? { description: s.text } : {}), pattern: s.text, query: s.text, url: s.text });
const eventsOf = (steps, running) => steps.flatMap((s, i) => {
  const id = `t${i}`;
  if (s.k === "tool") return [{ type: "tool_call", name: s.name, detail: { tool_call_id: id, args: argsOf(s) } },
    ...(running && i === steps.length - 1 ? [] : [{ type: "tool_result", name: id, detail: { tool_call_id: id, result: "" } }])];
  if (s.k === "plan") return [{ type: "tool_call", name: "TodoWrite", detail: { tool_call_id: id, args: { todos: s.items || [] } } },
    { type: "tool_result", name: id, detail: { tool_call_id: id, result: "" } }];
  if (s.k === "said") return [{ type: "progress", name: "text", detail: s.text }];
  if (s.k === "thought") return [{ type: "progress", name: "thinking", detail: s.text }];
  if (s.k === "error") return [{ type: "error", detail: { result: s.text } }];
  return s.text ? [{ type: "progress", name: "note", detail: s.text }] : [];
});

// AN EDIT IS ITS OWN ROW, its diff behind it: "Edited budget.py (+12 −3)" - a Write that made the file is "Wrote" (the general chat folds a run
// of edits into "Changed 3 files"; a coding chat is where the owner reviews each one)
const isEdit = (s) => s.k === "tool" && (!!s.edit || (!!s.file && describeCall(s.name, argsOf(s)).kind === "edit"));
export const editRow = (s) => {
  const hunks = editHunks(s.edit), { plus, minus } = stat(hunks), file = s.file || argsOf(s).file_path || "";
  const wrote = /^(write|writefile|createfile)$/i.test(String(s.name || "").replace(/[^a-z]/gi, "")) || (hunks.length && hunks.every((h) => h.lines.every((l) => l[0] === "+")));
  const verb = wrote ? "Wrote" : "Edited";
  return { type: "edit", file, summary: `${verb} ${baseName(file) || "a file"}${hunks.length ? ` (+${plus} −${minus})` : ""}`, plus, minus, hunks };
};

// THE PLAN IS A CHECKLIST, the newest one of the turn where it was last updated - never "Updated its plan (3 steps)" six times over
const PLAN_MARK = { completed: "done", done: "done", in_progress: "now", now: "now" };
export const planRow = (s) => ({ type: "plan", items: (s.items || []).filter((x) => x?.text).map((x) => ({ text: x.text, state: PLAN_MARK[x.status] || "todo" })) });

// a turn's own parts in order: its words, a fold of the work it did, each edit with its diff, its plan
export function turnParts(steps, { running = false } = {}) {
  const parts = [], run = [];
  const flush = (last) => {
    if (!run.length) return;
    for (const st of stepsOf(eventsOf(run, running && last), { keepStart: false })) {
      if (st.kind === "said") parts.push({ type: "said", text: st.summary });
      else { const w = parts.at(-1)?.type === "work" ? parts.at(-1) : (parts.push({ type: "work", steps: [] }), parts.at(-1)); w.steps.push(st); }
    }
    run.length = 0;
  };
  steps.forEach((s, i) => {
    if (isEdit(s)) { flush(false); parts.push(editRow(s)); }
    else if (s.k === "plan" && s.items?.length) { flush(false); parts.push(planRow(s)); }
    else run.push(s);
    if (i === steps.length - 1) flush(true);
  });
  const lastPlan = parts.map((p) => p.type).lastIndexOf("plan");
  return parts.filter((p, i) => p.type !== "plan" || i === lastPlan).map((p, i) => ({ ...p, id: `p${i}` }));
}

// ── the chat: what came in, what the owner said, and each turn - oldest first ────────────────────
const at = (x) => String(x || "").replace("T", " ").slice(0, 19);
export function chatRows({ sessions = [], mails = [] } = {}) {
  const rows = [];
  sessions.forEach((ses, si) => {
    const steps = (ses.source === "acp" ? stepsFromAcp(ses.updates) : ses.steps || []).map((s) => ({ ...s, at: at(s.at) || at(ses.at) }));
    const live = !!ses.live && si === sessions.length - 1;
    let turn = null;
    const close = () => { if (turn) rows.push(turn); turn = null; };
    steps.forEach((s) => {
      if (s.k === "you" || s.k === "brief") { close(); if (s.k === "you" && s.text) rows.push({ kind: "you", at: s.at, text: s.text }); return; }
      if (s.k === "gap" || s.k === "screen") return;
      if (!turn) turn = { kind: "turn", at: s.at, sid: ses.sid, steps: [] };
      turn.steps.push(s);
    });
    close();
    // ...its newest turn is the one at work while its CLI runs
    const last = rows.at(-1);
    if (live && last?.kind === "turn" && last.sid === ses.sid) last.running = true;
  });
  // ...each mail where it came in: over the first entry at or after it, a run of them one row (the general chat's Arrived)
  const out = [], pending = [...mails].sort((a, b) => at(a.joined || a.at).localeCompare(at(b.joined || b.at)));
  const take = (upto) => { const got = []; while (pending.length && (upto == null || at(pending[0].joined || pending[0].at) <= upto)) got.push(pending.shift()); if (got.length) out.push({ kind: "mail", at: at(got.at(-1).at), mail: got }); };
  for (const r of rows) { if (r.at) take(r.at); out.push(r); }
  take(null);
  return out.map((r, i) => (r.kind === "turn"
    ? { kind: "turn", id: `r${i}`, at: r.at, running: !!r.running, parts: turnParts(r.steps, { running: !!r.running }), answer: lastSaid(r.steps) }
    : { ...r, id: `r${i}` }));
}
const lastSaid = (steps) => [...steps].reverse().find((s) => s.k === "said")?.text || "";

// what a turn did, counted for its fold's line: "6 steps"
export const workCount = (p) => (p.steps || []).filter(isWork).length;

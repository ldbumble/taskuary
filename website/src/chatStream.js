// ONE STREAM, ONE MAPPER (the owner, 2026-11-06: "one shared chat object for coding and regular ... combine the code as much as possible").
// Every task's agent draws in the one chat (GeneralWorkspace.jsx), and every source it reads becomes ONE row shape here:
// - a general agent's run trace (general.shown_history's messages, the session's live `trace`) - trace events as agents.py writes them;
// - a turn of the task's one list (conversation.items): its steps in the log's shape ({k, text, name, args, file, edit, at} - a CLI's own log
//   as sessionrecord reads it, an ACP session's updates as conversation.acp_steps does), read into trace events (eventsOf).
// Trace events are the one currency: turnParts reads them into a turn's parts - its words, its work (agentSteps.stepsOf, one line a step),
// each edit its own row with its diff ("Edited budget.py (+12 −3)"), its plan a checklist. Whatever drew them, a turn is those parts.
import { baseName, describeCall, isWork, present, stepsOf } from "./agentSteps.js";
import { editHunks, stat } from "./diffView.js";
import { isSignin } from "./browserSplit.js";
import { liveTerminal } from "./taskLayout.js";
import { filesOf, SHOW, viewOf } from "./viewSpec.js";
import { plural } from "./timeWords.js";

// ── a coding session's steps -> trace events, the one currency ───────────────────────────────────
// a step the record kept without its arguments (saved before they were) is read off its one line of text
const argsOf = (s) => (s.args && Object.keys(s.args).length ? s.args
  : { file_path: s.file || s.text, command: s.detail || s.text, ...(s.detail ? { description: s.text } : {}), pattern: s.text, query: s.text, url: s.text });
// ...a call over ACP is running until ACP says it ran (`status`); a log's, until something came after it. A turn that is over has nothing running
const OVER = ["completed", "failed"];
// ...and a call put to the owner (permissions.calls) is neither: `held` waits on his answer, `refused` was never run - drawn as either, it read
// "Deleted ledger-archive" over the card that asked for it, and after his Reject too (the stress round, 2026-11-18)
const ASKED = { held: "Taskuary held this for the owner - it waits for your answer on its card.", refused: "Not run - nobody allowed it.", rejected: "Not run - you said no." };
// ...and HIS ANSWER ON ITS ROW is the one record of it (chatlog.asked_answered - no press line besides): his no reads as his, never "nobody"
const askedOf = (s) => (ASKED[s.status] ? s.status : String(s.answer || "").startsWith("reject") && s.status !== "completed" ? "rejected" : "");
const runs = (s, running, last) => running && !askedOf(s) && (s.status ? !OVER.includes(s.status) : last);
// ...and one ACP still called pending or running when nothing runs any more NEVER FINISHED - a permission left open when Taskuary restarted, a
// session that died mid-call: drawn done, "Edited totals.py" read as made (the stress round, 2026-11-10)
const ended = (s, output, a = askedOf(s)) => (a ? { result: ASKED[a], is_error: true, state: a === "held" ? a : "refused" } : s.status && !OVER.includes(s.status) ? { result: output || "It never finished.", is_error: true }
  : { result: output, is_error: s.status === "failed" });
// A TURN WITH ITS FAILED LINE SAYS THE FAILURE ONCE (chatlog.read's rule, on the steps the open chat patched in as they came - walk 19: "No AI is
// connected" stood twice, the error step pushed live and the turn's own line under it)
export const turnSteps = (t) => (t?.fail ? (t.steps || []).filter((s) => s.k !== "error") : t?.steps || []);
export const eventsOf = (steps, running, tail = true) => steps.flatMap((s, i) => {
  const id = s.id || `t${i}`, output = String(s.output || "").trim();
  if (s.k === "tool") return [{ type: "tool_call", name: s.name, detail: { tool_call_id: id, args: argsOf(s), output,
      ...(s.parent ? { parent: s.parent } : {}), ...(s.edit ? { edit: s.edit } : {}), ...(s.file ? { file: s.file } : {}),
      ...(s.outcome ? { outcome: s.outcome } : {}), ...(s.why ? { why: s.why } : {}), ...(s.times > 1 ? { times: s.times } : {}), ...(s.did ? { did: s.did } : {}),
      // ...the agent's own words for it - its title, its kind, its files (agentSteps.agentWords) - and the options of a permission it waits on
      ...(s.title ? { title: s.title } : {}), ...(s.tool_kind ? { tool_kind: s.tool_kind } : {}), ...(s.paths?.length ? { paths: s.paths } : {}), ...(s.ask?.length ? { ask: s.ask } : {}), ...(s.call ? { call: s.call } : {}) } },
    ...(runs(s, running, tail && i === steps.length - 1) ? [] : [{ type: "tool_result", name: id, detail: { tool_call_id: id, ...ended(s, output) } }])];
  if (s.k === "plan") return [{ type: "tool_call", name: "TodoWrite", detail: { tool_call_id: id, args: { todos: s.items || [] } } },
    { type: "tool_result", name: id, detail: { tool_call_id: id, result: "" } }];
  if (s.k === "said") return [{ type: "progress", name: "text", detail: s.text, ...(s.id ? { id: s.id } : {}) }];
  if (s.k === "thought") return [];                    // ...a model's private reasoning is never a step (conversation._said)
  if (s.k === "error") return [{ type: "error", ...(s.name ? { name: s.name } : {}), detail: { result: s.text } }];      // ...by the call it came from
  return s.text ? [{ type: "progress", name: "note", detail: s.text }] : [];
});

// ── a tool call that is an EDIT, and one that is a PLAN ─────────────────────────────────────────
// AN EDIT IS ITS OWN ROW, its diff behind it: THE CALL'S OWN DIFF (the owner, 2026-11-23: adopt the open-source model) - an ACP agent's `diff`
// content, a trace road's said as one where its input is the edit (conversation.acp_of_trace), a log's own record (`edit`) - never one guessed
// here from the arguments it was handed
const FILE_KEYS = ["file_path", "path", "filePath", "absolute_path"];
// ...but an edit that FAILED or never ran is no edit made: drawn "Edited totals.py (+1 −1)" from the diff it asked to make, it read as done -
// it is its step, drawn failed (the stress round, 2026-11-10)
export function editOf(e, res, running = false) {
  if (e?.type !== "tool_call" || res?.detail?.is_error) return null;
  const d = e.detail || {}, a = d.args || {};
  if (!d.edit && describeCall(e.name, a).kind !== "edit") return null;
  const edit = d.edit || null, file = d.file || FILE_KEYS.map((k) => a[k]).find(Boolean) || "";
  // ...a log's own edit row stands even with no diff kept; a trace's call is a row of its own only when it carries one
  return edit || d.file ? editRow({ name: e.name, edit, file, running: running && !res }) : null;
}
export const editRow = (s) => {
  const hunks = editHunks(s.edit), { plus, minus } = stat(hunks), file = s.file || "";
  const wrote = /^(write|writefile|createfile)$/i.test(String(s.name || "").replace(/[^a-z]/gi, "")) || (hunks.length && hunks.every((h) => h.lines.every((l) => l[0] === "+")));
  // ...an edit still being made is "Editing x", never "Edited x (+1 −1)" over a call that has not returned (and the working line says it, workingLine)
  // - its verb in the present by the one table every running step is worded by (agentSteps.present), never a pair of its own
  const did = wrote ? "Wrote" : "Edited", verb = s.running ? present(did) : did;
  return { type: "edit", file, wrote: !!wrote, running: !!s.running, summary: `${verb} ${baseName(file) || "a file"}${hunks.length && !s.running ? ` (+${plus} −${minus})` : ""}`, plus, minus, hunks };
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
// in order: its words, a fold of the work it did, each edit with its diff, each view it showed, its plan - THE SAME WHILE IT WORKS AND ONCE IT
// IS FILED (the owner, 2026-11-23: words stay where they were said): nothing is moved, merged or taken out when the turn ends; the answer's
// own repeat of its words is the server's to leave out (chatlog.read `tail`). A call's result is its own wherever it came - a run of steps
// cut by an edit keeps the results that arrived after the edit, so nothing it started is left spinning
export function turnParts(events, { keepStart = false, live = false } = {}) {
  const evs = (events || []).filter(Boolean), results = new Map(), parts = [], special = new Set();
  for (const e of evs) if (e.type === "tool_result") results.set(e.detail?.tool_call_id || e.name, e);
  let run = [], first = true;
  const flush = () => {
    if (!run.length) return;
    const ids = new Set(run.filter((e) => e.type === "tool_call").map((e) => e.detail?.tool_call_id));
    const got = [...ids].map((id) => results.get(id)).filter(Boolean);
    for (const st of stepsOf([...run, ...got], { keepStart: keepStart && first })) {
      if (st.kind === "said") parts.push({ type: "said", text: st.summary, id: st.id });
      else { const w = parts.at(-1)?.type === "work" ? parts.at(-1) : (parts.push({ type: "work", steps: [], id: st.id }), parts.at(-1)); w.steps.push(st); }
    }
    run = []; first = false;
  };
  for (const e of evs) {
    if (e.type === "tool_result") continue;
    // ...and a VIEW the agent showed (agenttools `show`) is its own part, drawn as the UI it describes (ViewSpec.jsx)
    // ...and the FILES it showed with it (viewSpec.filesOf): the pictures themselves, over any view the same call drew
    // ...each part by the call it is of (its row's own id in the log), never by where it falls: one drawn later never re-keys those after it
    const cid = e.detail?.tool_call_id, res = results.get(cid), ps = [filesOf(e, res), editOf(e, res, live) || planOf(e) || viewOf(e, res)].filter(Boolean)
      .map((p, j) => ({ ...p, id: j ? `${cid}:${j}` : cid }));
    if (ps.length) { flush(); special.add(cid); parts.push(...ps); } else run.push(e);
  }
  flush();
  // ...an edit that failed and was then made is no failure (agentSteps' `recovered`): Claude's first try at a string not found, its second made
  // ...and so is a view that failed and was then drawn, whatever it was titled the second time (walk 21: "could not show you" over the chart)
  const made = (s, q) => (s.kind === "edit" ? q.type === "edit" && q.summary.startsWith(s.summary) : SHOW.test(String(s.tool || "")) && q.type === "view");
  parts.forEach((p, i) => p.type === "work" && p.steps.forEach((s) => { if (s.status === "error" && parts.slice(i + 1).some((q) => made(s, q))) s.status = "recovered"; }));
  // ...and its plan is the one row the agent keeps replacing (chatlog: one per plan, in place) - never a filter keeping the last of several
  return parts.map((p, i) => ({ ...p, id: p.id || `p${i}` }));
}
// what a turn did, counted for its fold's line: "6 steps" - its edits each one
export const workCount = (parts) => workRows(parts).length;
// ONE LAYOUT, AT WORK AND FILED (the owner, 2026-11-23: "the live layout IS the finished layout"): a turn's parts in the order they came, what it
// said and showed standing where it said it, each run of work between them one fold of its own - keyed by its first part, so a run that grows,
// and the turn's end, leave every fold where it was and as he left it (open or shut). A grouping that wraps rows, never one that moves them
export const SHOWN_PARTS = ["said", "view", "files"];
export const runsOf = (parts) => (parts || []).reduce((out, p) => {
  if (SHOWN_PARTS.includes(p.type)) out.push({ id: p.id, parts: [p] });
  else if (out.at(-1)?.fold) out.at(-1).parts.push(p);
  else out.push({ id: p.id, fold: true, parts: [p] });
  return out;
}, []);
// A PERMISSION ASKED IS ON ITS CALL'S ROW (the owner, 2026-11-23: "just permissions to push something" in the row, Zed-style - action cards
// stay cards): the request waiting on him (permissions.pending, by the call it names) drawn on that row, each option by the agent's own name
// for it where it gave one; the requests no row in the list names stand as their card, as before
export const askOn = (step, byCall) => {
  const p = step?.call && byCall?.get?.(step.call);
  if (!p) return null;
  const named = new Map((step.ask || []).map((o) => [o.kind, o.name]));
  return { p, options: (p.options || []).map((o) => ({ kind: o.kind, label: named.get(o.kind) || o.label })) };
};
export const asksOff = (perms, items) => {
  const calls = new Set((items || []).flatMap((x) => (x.kind === "turn" ? (x.steps || []).map((s) => s.call).filter(Boolean) : [])));
  return (perms || []).filter((p) => !p.call || !calls.has(p.call));
};
// THE ROWS THE SERVER PUSHED AS IT WROTE THEM (chatlog.pushed - a message as it streams, a call as it moves): each patched into its turn in
// place, by its own id, or added at the turn's foot where it is new - the list's next read is the same rows, so nothing moves when it lands
export const patchSteps = (list, pushed, tid) => {
  const by = new Map();
  for (const p of pushed || []) if (p?.step?.id && String(p.tid) === String(tid)) by.set(p.turn, [...(by.get(p.turn) || []), p.step]);
  if (!list?.items || !by.size) return list;
  let hit = false;
  const items = list.items.map((x) => {
    const ss = x.kind === "turn" && by.get(x.id);
    if (!ss) return x;
    const steps = [...(x.steps || [])];
    for (const s of ss) { const i = steps.findIndex((y) => y.id === s.id); if (i >= 0) steps[i] = s; else steps.push(s); }
    hit = true;
    return { ...x, steps };
  });
  return hit ? { ...list, items } : list;
};
// A FINISHED TURN RIGHT AFTER A TURN IS DRAWN UNDER ITS HEAD - the work going on (a second turn of its session, a wake, its answer filed after) - never
// one after a failure (Try again's turn stands under the failure it is past), never one at work (its own head, its clock and Stop)
export const folds = (prev, x) => prev?.kind === "turn" && prev.state !== "failed" && x?.kind === "turn" && x.state !== "working" && x.state !== "starting";
// ...AND THAT HEAD'S CLOCK IS ALL OF IT (the owner, 2026-11-23: "ran 1m 15s" over steps that went on for five minutes): every turn drawn under it,
// run for run - each to its last step (chatlog.run_of) - so a wake hours later adds its own minutes, never the hours between. Seconds
export const ranUnder = (items, i) => {
  let s = 0;
  for (let j = i; j < (items || []).length && (j === i || folds(items[j - 1], items[j])); j += 1) s += Number(items[j].ran) || 0;
  return s;
};
// ...a helper's own steps among them (walk 5: "4 steps" stood five minutes while the helper under one of them did all the work)
const withKids = (ss) => ss.filter(isWork).flatMap((s) => [s, ...withKids(s.kids || [])]);
const workRows = (parts) => (parts || []).flatMap((p) => (p.type === "edit" ? [p] : p.type === "work" ? withKids(p.steps) : []));
// ...AND ITS ONE LINE SAYS THE ROWS IT OPENS ON (the real-Claude walk, 2026-11-19: "3 steps - ran 2 commands, used a tool" opened on two rows,
// and "1 step - used a tool" named nothing): counted from those rows, in their own words - the first few, then how many more
const FEW = 3;
const lower = (t) => String(t || "").replace(/^[A-Z](?![A-Z])/, (c) => c.toLowerCase());
// ...and rows of one kind say it once, counted (walk 5: "read 3 web pages, read 4 web pages" - two runs of reads cut by a sentence)
const KIND_SAID = { read: (k) => `read ${plural(k, "file")}`, page: (k) => `read ${plural(k, "web page")}`, run: (k) => `ran ${plural(k, "command")}`,
  edit: (k) => `changed ${plural(k, "file")}`, search: (k) => `searched files ${k} times`, web: (k) => `searched the web ${k} times`, mail: () => "searched your mail" };
const calls = (r) => r.n || 1;
// ...ONE COUNTING UNIT (the judge's walk, 2026-11-19: "1 step - ..., and 2 more" - the head counted rows, the tail counted calls): every
// number is of calls - a row folding three calls is three steps - and "and N more" is the steps the named words did not cover
const callsOf = (r) => (r.type === "edit" ? 1 : calls(r));
export const foldLine = (parts) => {
  const rows = workRows(parts), n = rows.reduce((t, r) => t + callsOf(r), 0);
  if (!n) return "";
  const kinds = [], by = new Map();
  for (const r of rows) { const k = r.type === "edit" ? "edit" : r.kind; if (!by.has(k)) { by.set(k, []); kinds.push(k); } by.get(k).push(r); }
  // ...and a row that is its command (agentSteps `code`) is counted, never quoted: the line read "1 step - ran $p = '..\..\attachments…'" (walk 18)
  const words = kinds.flatMap((k) => { const rs = by.get(k), c = rs.reduce((t, r) => t + callsOf(r), 0);
    return (rs.length > 1 || rs.some((r) => r.code)) && KIND_SAID[k] ? [[KIND_SAID[k](c), c]] : rs.map((r) => [lower(r.summary), callsOf(r)]); }).filter(([w]) => w);
  const said = words.slice(0, words.length > FEW ? FEW - 1 : FEW), more = n - said.reduce((t, [, c]) => t + c, 0);
  return `${plural(n, "step")}${said.length ? ` - ${said.map(([w]) => w).join(", ")}${more > 0 && words.length > said.length ? `, and ${more} more` : ""}` : ""}`;
};
// A DRAFT WHERE IT STOOD, no longer the one to press (GeneralWorkspace wasCard, NotSent): the list's card in one of these states, carrying what it said
export const isPastCard = (c) => ["superseded", "passed", "withdrawn", "rejected"].includes(c?.status) && !!c.was;
// ...AND AN EARLIER VERSION NEVER TAKES ITS REVIEW'S OWN CARD (recorded 2026-11-15: a reply the agent rewrote and he then sent - the rewrite
// is the same review - left no "Sent" card at all: the earlier draft's record, drawn first, had claimed every card of that review): the
// reviews that still have a card of their own in the list, whatever earlier versions of them stand above it
export const standing = (items) => new Set((items || []).flatMap((x) => (x.kind === "card" ? [x] : x.kind === "turn" ? x.cards || [] : []))
  .filter((c) => !isPastCard(c)).map((c) => c.review));
export const hasParts = (parts) => (parts || []).some((p) => p.type !== "said" || p.text);

// WHICH SOURCE a task's chat reads: a coding task, or any task with a coding CLI live on it, is its sessions (codingchat.py); every other is
// the general agent's conversation (general.py). The one component draws either - this picks, nothing in the page does
export const chatSource = (task, term) => (task?.Kind === "coding" || liveTerminal(term) ? "coding" : "general");
// WHAT WAITS BY THE BOX, WHEN MANY DO (decided 2026-11-12): the NEWEST lines and the count - the strip scrolled from the oldest, so the line he
// had just typed stood out of sight under a dozen older ones. A line that failed to go in is kept where it is wherever it stands
export const WAIT_SHOWN = 4;
export const waitingShown = (items, k = WAIT_SHOWN) => (items.length <= k ? items : items.filter((x, i) => i >= items.length - k || x.err));

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
/* IS THE CHAT STILL HELD AT ITS END, after a scroll event (the owner, 2026-11-11: "task should open on last thing not randomly in middle")?
   Only HIS OWN scroll up lets go of it (`own`: a wheel, a finger, a key or a press just before; `top` under `was`), and coming back to the end
   takes it again. A scroll event that finds the end far away is NOT him: the chat grew between the pin and the event - forty "Show all"
   buttons measured in after the first draw, a picture getting its size - and reading that as "he moved away" left a long chat opened ~900px
   short of its end, never to follow again. */
export const AT_END = 56;
export const heldAtEnd = (held, { top, was, gap, own }) => gap < AT_END || (held && !(own && top < was - 1));
// ...AND AWAY FROM ITS END, WHAT HE WAS READING STAYS WHERE IT WAS (walk 12, recorded: the browser pane opened and shut beside the chat, every line
// re-wrapped to the new width, the chat grew from 997 to 1502 px and back, and what he read jumped ~500 px each time). The row at the top of the
// view - the deepest one still taller than the view gives way to its child - is marked with its offset, and after a change of size the view is
// moved by however far that row went
export const anchorOf = (view, root, depth = 5) => {
  if (!view || !root) return null;
  const top = view.getBoundingClientRect().top, h = view.clientHeight;
  let el = null, rows = [...root.children];
  for (let d = 0; d < depth && rows.length; d += 1) {
    const hit = rows.find((r) => r.getBoundingClientRect().bottom > top);
    if (!hit) break;
    el = hit;
    if (hit.getBoundingClientRect().height <= h) break;
    rows = [...hit.children];
  }
  return el ? { el, off: el.getBoundingClientRect().top - top } : null;
};
// ...AND AT ITS END A FOLD IS NOT A MOVE OF ITS OWN (walk 17, recorded: on "✓ Sent" the pressed card folded before the next one was drawn, and
// the chat flicked up 400 px and back down within 0.2 s): held at its end, the chat keeps the height it had for SHRINK_HOLD ms, so the fold and
// what comes under it are one move. `tall`: its height before; `now`: its own height now - the height to keep, or 0
export const SHRINK_HOLD = 500;
export const shrinkHeld = (held, tall, now) => (held && now < tall - 1 ? tall : 0);
export const anchorShift = (view, a) => (a?.el?.isConnected ? a.el.getBoundingClientRect().top - view.getBoundingClientRect().top - a.off : 0);
/* A CHAT OPENS AT THE START OF ITS NEWEST REPLY (the owner, 2026-11-24): opened at its very bottom, a long answer was read from its last lines up.
   The top of the newest row - the turn its trailing cards belong to - goes to the top of the view, or the end where that is nearer (a short
   reply, a chat that fits). -> the scrollTop to open at. Held there for OPEN_HOLD ms while rows measure themselves in, unless he moves first */
export const OPEN_HOLD = 1000;
export const openAt = (view, root) => {
  const end = view.scrollHeight - view.clientHeight;
  if (end <= 0 || !root) return Math.max(0, end);
  const rows = [...root.querySelectorAll("[data-tq-item]")].filter((r) => !r.parentElement?.closest("[data-tq-item]"));
  let i = rows.length - 1;
  while (i > 0 && rows[i].hasAttribute("data-tq-row-cards")) i -= 1;
  if (i < 0) return end;
  const top = rows[i].getBoundingClientRect().top - view.getBoundingClientRect().top + view.scrollTop;
  return Math.max(0, Math.min(end, Math.round(top)));
};

// THE CHAT'S OWN LIST ON THE PAGE (GeneralWorkspace): what is drawn is the server's list (conversation.items), with two things of the page's -
// THE LIST ASKED LAST: the one this view last read, or one read ahead with its task as he came back to it (taskDetail.prefetchTask) - an older
// read is never drawn over a newer one (the owner's live task, 2026-11-12: he left a task and came back); `_at` is when each was ASKED
export const newerList = (a, b) => (!a ? b || null : !b ? a : (b._at || 0) > (a._at || 0) ? b : a);
// ...WHAT A CHAT MAY PAINT BEFORE ITS OWN READ LANDS (the owner, 2026-11-13: a long task opened on messages from his last visit, the rest
// coming in after - "if you need time to load full convo then just spin, don't open with weird data"): only a list read a moment ago - the
// view drawn again as its session starts, one read ahead for Next. An older one is not painted; the chat spins until its read lands
export const HELD_FOR = 15000;
export const paintable = (own, ahead, now = Date.now()) => newerList(own && now - (own._at || 0) < HELD_FOR ? own : null, ahead || null);
/* ...AND HIS OWN LINES: a line it sent is drawn at once - in the conversation when the agent was at rest (it is heard as it is sent, its turn
   under it), by the box when a turn was at work - and the server's copy takes over by the same name.
   ...ABOVE THE TURN HIS LINE BEGAN (the owner's live task, 2026-11-12: back on a task, he typed - the dots stood above "try now"): a read that
   already has that turn starting, with nothing in it, and not yet his line - the line goes over it, never under */
export const withMine = (list, mine) => {
  const items = list?.items || [], pending = list?.pending || [], known = new Set([...items, ...pending].map((x) => x.id));
  const own = mine.filter((l) => !known.has(l.id));
  // ...A LINE WHOSE SEND FAILED STAYS WHERE IT STANDS, in its own words (the owner's live task, 2026-11-12: it went down by the box, red, the
  // app's error glued to his words): the failure is one line under it with Try again (ConvLine), and no turn starts under it
  const rest = own.filter((l) => l.rest), wait = own.filter((l) => !l.rest);
  // ...and the turn it begins under it while the server's read has none yet - at rest, or at work in the beat before his line is filed there
  const live = (x) => x?.kind === "turn" && ["starting", "working"].includes(x.state);
  const tail = rest.some((l) => !l.err) && (!list?.working || !live(items.at(-1))) ? [{ id: `t:${rest.at(-1).id}:0`, kind: "turn", state: "starting", steps: [], text: "", cards: [], started: +rest.at(-1).at / 1000 }] : [];
  const at = items.length && rest.length && ((x) => x.kind === "turn" && ["starting", "working"].includes(x.state) && !x.text && !(x.steps || []).length)(items.at(-1)) ? items.length - 1 : items.length;
  // ...AND A REPLY DRAFT ABOVE IT GREYS IN ITS PLACE FROM THE SAME FRAME (the owner, 2026-11-12: "grey out buttons right away"): what the
  // server does as it hears the line (proposals.set_aside_drafts), drawn before its read comes back - its buttons stood lit ~300 ms
  // ...a line sent while a turn works too (the owner, 2026-11-16: "The second a new prompt comes in ... it should gray out the action card but never move")
  // ...the same card, its buttons greyed, no line saying why (the owner, 2026-11-18): the server marks each card his line would grey (`aside`)
  const by = own.findLast((l) => !l.err);
  // ...ONLY A CARD THAT STOOD BEFORE HIS LINE (a walk, 2026-11-18): a Post card raised twelve seconds after his line was drawn greyed "you wrote
  // ... after it" - he never saw it lit. A card from his line's own second on is the answer to it (the server's rule: proposals._older)
  const before = (c) => !c.at || +new Date(String(c.at).replace(" ", "T")) + 1000 <= +new Date(by.at);
  const aside = (c) => (by && c.status === "pending" && (c.was || c.aside) && before(c) ? { ...c, status: "passed" } : c);
  // ...AND HIS LINE KEEPS ITS WORDS THROUGH THE SWAP (the owner, live 2026-11-20: his line showed, vanished, came back): the server places his
  // line the moment it is heard and fills its words a beat later, when its row is filed - in that beat its item had no words and drew nothing.
  // One identity from the send: the server's item takes the place, the words he sent stay in it until the server's own arrive
  const sent = new Map(mine.map((l) => [l.id, l]));
  const said = (x) => (x.kind === "line" && !String(x.text || "").trim() && sent.has(x.id) ? { ...x, text: sent.get(x.id).text, files: x.files?.length ? x.files : sent.get(x.id).files || [] } : x);
  const greyed = items.map((x) => (x.kind === "card" ? aside(x) : x.kind === "turn" && (x.cards || []).length ? { ...x, cards: x.cards.map(aside) } : said(x)));
  return { items: [...greyed.slice(0, at), ...rest, ...greyed.slice(at), ...tail], pending: [...pending, ...wait] };
};
// THE BASIC FLOW OF WHAT THE PAGE DRAWS (conversation.flow_breaks, the page's half): his newest line has no turn at work above it, and
// nothing already drawn changes place or has anything new drawn above it (`was`: the list drawn before). [] when it reads like a chat
export const flowBreaks = (now, was = null) => {
  const xs = now?.items || [], out = [], ids = xs.map((x) => x.id), live = (x) => x.kind === "turn" && ["starting", "working"].includes(x.state);
  const his = xs.map((x) => x.kind === "line").lastIndexOf(true);
  xs.slice(0, Math.max(his, 0)).forEach((x) => { if (live(x)) out.push(`a: the turn at work ${x.id} stands above his newest line ${ids[his]}`); });
  if (!was) return out;
  const old = (was.items || []).map((x) => x.id), set = new Set(old), kept = old.filter((i) => ids.includes(i));
  if (JSON.stringify(ids.filter((i) => kept.includes(i))) !== JSON.stringify(kept)) out.push("f: items already drawn changed their order");
  const top = Math.max(-1, ...kept.map((i) => ids.indexOf(i)));
  ids.slice(0, Math.max(top, 0)).forEach((i) => { if (!set.has(i)) out.push(`f: ${i} is drawn above ${ids[top]}, which was already there`); });
  old.forEach((i) => { const x = was.items.find((y) => y.id === i); if (!ids.includes(i) && !(live(x) && !x.text && !(x.steps || []).length)) out.push(`c: ${i} was on the canvas and is gone`); });
  return out;
};
// THE WAITING ROOM'S MESSAGES ARE COUNTS ON THEIR SENDER'S CHIP (the owner, 2026-11-12: "From Cat Priem · 2 new"): what came in and the agent
// has not heard yet, one chip per sender - his own replies on another channel one per channel ("You on WhatsApp · 1") - each naming the
// items it stands for (`ids`), so one item is in one place. `came`: the label of the chip the box already wears for where the task came
// from - a sender's count joins it rather than stand beside it
const CHANNELS = { email: "email", whatsapp: "WhatsApp", teams: "Teams", telegram: "Telegram", slack: "Slack", sms: "SMS" };
export const waitingChips = (pending, came = "") => {
  const by = new Map();
  for (const x of pending || []) {
    if (x.kind !== "arrival") continue;
    const base = x.own ? `You on ${CHANNELS[String(x.channel || "").toLowerCase()] || x.channel || "another channel"}` : `From ${x.who || "someone"}`;
    by.set(base, [...(by.get(base) || []), x.id]);
  }
  return [...by].map(([base, ids]) => ({ key: base, came: !!came && base === came, ids,
    label: `${base} · ${ids.length}${base.startsWith("You on") ? "" : " new"}` }));
};
// THE WORKING LINE SAYS WHAT IS HAPPENING, AND WHAT WE ARE WAITING FOR (the owner, 2026-11-12: "in summary it says what its doing while it's
// working instead of just ... which means nothing"; and on every level, "what it's doing and what are we waiting for"): one line beside a turn's
// dots, from what the list already holds - what the turn waits on him for (`ask`), else the newest step at work in its own words
// (agentSteps.stepLabel), else the model writing; a turn not begun yet waits for its agent to start. Plain code, never a model call
// ...but only the CHAT'S FIRST turn says it waits for its agent (the owner, 2026-11-16, mid-conversation on a session gone idle: "Waiting for the
// agent to start" is the app's mechanics) - a `later` turn starting is the work going on, and reads as the turn it becomes: bare dots stood
// over it, then words (the walks, 2026-11-17). One whose CLI is opening is not `later` (ConvTurn), so a later line never steps back
// `doing`: the answer it is writing, while that is the newest thing it did (conversation `doing`)
// ...AND NEVER THE WORDS OF A ROW IN SIGHT (the status walk, 2026-11-18: a short thought's row and the line under it read "The budget note comes
// first, then the archive" at one beat; with the fold opened, "Reading budget.md" stood as a row and again on the line under it at every tool
// beat). One structural test, for a thought and a step alike: is the row that holds those words drawn open right now - a turn's rows stand open
// while it has no work to fold (TurnWorkView), and inside a fold he opened or the dock's trail (`open`); shut in the fold, the line names it
export const workingLine = (parts, label, { starting = false, later = false, ask = "", thinking = "", open = false } = {}) => {
  if (ask) return ask;
  // the newest thing the turn did: its last step, or an edit made after it (an edit is a part of its own, editRow)
  const newest = (parts || []).flatMap((p) => (p.type === "work" ? (p.steps || []).map((st) => ({ st, row: String(label(st) || "") }))
    : p.type === "edit" ? [{ edit: p, row: p.summary }] : [])).at(-1);
  const inSight = open || workCount(parts) === 0;
  const say = (line, held) => (line && !(inSight && flat(newest.row).includes(flat(line))) ? line : held);
  // ...an edit being made, or a step at work, is the newest thing at work, in its own words (editRow `running`, stepLabel)
  if (newest?.edit?.running) return say(newest.edit.summary, "Working…");
  if (newest?.st?.status === "running") return say(newest.row.split(/\r?\n/)[0].trim(), "Working…");
  // ...and WHAT IT IS THINKING, while that is the newest thing it does (the owner, 2026-11-16: "Thinking..." for three minutes with nothing else):
  // the thought's latest words, as it writes them (chatlog._now `thinking`) - the one place a thought reads, never a step row (conversation._said)
  if (thinking && thinkingLine(thinking)) return thinkingLine(thinking);
  return !newest && starting && !later ? "Waiting for the agent to start" : "Thinking…";
};
const flat = (t) => String(t || "").replace(/\s+/g, " ").replace(/[.…]+$/, "").trim();
// a thought as one short line: its last sentence, cut at a word
export const thinkingLine = (text) => {
  // ...never Taskuary's own marker as it streams in (the goal walk on Codex, 2026-11-22: "Writing: [["): words stop where one opens, even half-written
  const t = String(text || "").replace(/\[\[[\s\S]*$|\[$/, "").replace(/\s+/g, " ").trim().replace(/[.…]+$/, "");
  const s = t.split(/(?<=[.!?])\s+/).filter(Boolean).at(-1) || "";
  return s.length > 110 ? `…${s.slice(-108).replace(/^\S*\s/, "")}` : s;
};
// WHERE THE AGENT'S QUESTION IS DRAWN (the owner, 2026-11-13: "never ever pin items on the bottom of the chat"): in the turn that asked it,
// which the list names (conversation.items `asking.turn`) - "" only while that turn is not in what is drawn (a read behind, a chat with no
// turn yet), when it stands under everything as it did
export const askTurn = (asking, items) => (asking?.turn && (items || []).some((x) => x.kind === "turn" && x.id === asking.turn) ? asking.turn : "");
// ONE ACTION BOX AT A TIME, A HARD RULE (cardqueue.py; the owner's live task, 2026-11-19: a held browser step read "1 of 2 · next: the reply
// to Gail" and the reply's box stood under it): a card the line holds behind its front is drawn nowhere - the reply's block included, by its
// review (`rid`) - and while the front is another card, no door to write a reply stands beside it either (`replyDoorOpen`)
export const replyDoorOpen = (queue, rid) => !(queue?.live || []).length || (queue.live || []).includes(rid);
// ...and A MISSING FACT IS ONE QUESTION (the owner's rule; recorded on the real CLI, 2026-11-15): while the agent waits on his answer, the reply
// it could not write yet - no words, no email beside it - is not drawn under the question as an empty box over a greyed Send; his answer's
// turn writes it (the server's list leaves it out of the turn the same way, conversation.items)
const words = (r) => String(r?.FinalText || r?.DraftText || "").trim();
export const askedFirst = (asking, reviews = []) => !!asking && !(reviews || []).some((r) => r.Kind === "slot" && r.Status === "pending")
  && !(reviews || []).some((r) => ["draft_reply", "draft"].includes(r.Kind) && r.Status === "pending" && words(r));
// THE ONE TURN THAT OFFERS ITS TRY AGAIN (its summary's `retry`): the newest turn, at rest, with nothing of his under it (nothing new is drawn
// above his line), and never one whose own ask, card or letters wait: those ARE the step. What a turn left on him ("For you to do") is not this
// one's: each turn says its own, settled once by the list (conversation.left_on_him)
export const onYouTurn = (items, { askAt = "", lettersAt = "", landAt = "" } = {}) => {
  const xs = items || [], i = xs.map((x) => x.kind === "turn").lastIndexOf(true), t = xs[i];
  if (!t || ["starting", "working"].includes(t.state) || xs.slice(i + 1).some((x) => x.kind !== "arrival")) return "";
  return [askAt, lettersAt, landAt].includes(t.id) || (t.cards || []).some((c) => c.status === "pending") ? "" : t.id;
};
// ...what a turn at work waits on HIM for, in words: the step its session is stopped at, a sign-in, a question
// ...(a question the agent asked before is no wait while it works: the recorded walk, 2026-11-12, read "Waiting for your answer" over a turn
// already at work on his answer - only a step it is stopped at, or a sign-in on the page, holds a turn at work)
export const waitingOn = (list) => (list?.permissions?.length ? "Waiting for your Allow once"
  : isSignin(list?.asking) ? (list.asking.named ? list.asking.text : "Waiting for you to sign in") : "");      // ...a step the agent named, by its name

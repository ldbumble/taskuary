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
  const aside = (c) => (rest.length && c.status === "pending" && c.was ? { ...c, status: "passed" } : c);
  const greyed = items.map((x) => (x.kind === "card" ? aside(x) : x.kind === "turn" && (x.cards || []).length ? { ...x, cards: x.cards.map(aside) } : x));
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
export const workingLine = (parts, label, { starting = false, ask = "" } = {}) => {
  if (ask) return ask;
  const steps = (parts || []).filter((p) => p.type === "work").flatMap((p) => p.steps || []), last = steps.at(-1);
  if (!last) return starting ? "Waiting for the agent to start" : "Thinking…";
  return last.status === "running" ? String(label(last) || "").split(/\r?\n/)[0].trim() || "Working…" : "Thinking…";
};
// WHERE THE AGENT'S QUESTION IS DRAWN (the owner, 2026-11-13: "never ever pin items on the bottom of the chat"): in the turn that asked it,
// which the list names (conversation.items `asking.turn`) - "" only while that turn is not in what is drawn (a read behind, a chat with no
// turn yet), when it stands under everything as it did
export const askTurn = (asking, items) => (asking?.turn && (items || []).some((x) => x.kind === "turn" && x.id === asking.turn) ? asking.turn : "");
// WHERE THE LETTERS THAT WAIT FOR HIS SEND ARE DRAWN (the reply's card and the task's emails, one block of the page): at the end of the turn
// the list names (conversation.items `letters` - the last turn that left a letter still waiting), under that turn's words. "" while the
// list names none or holds no such turn yet, or while that turn is at work - it holds the block back, as it does its cards - and the page
// then hangs the block on the reply's own card, as it did. The owner's live task, 2026-11-13: an email a later turn wrote stood up at the
// reply's card, that turn's words under both
// ...nor above a line of his: what stood over the line he just sent is set aside as it is heard (proposals.set_aside_drafts), and the page
// draws that from the same frame (withMine) - the block's Send stood lit over his new line until the list was read again
// A CARD THE LIST PLACES NOWHERE STANDS UNDER EVERYTHING - ONCE THERE IS A LIST (the audit, 2026-11-13, recorded on Back and on a rail click): a
// task's cards arrive with the task, its conversation a beat later, and for that beat (1.5 s on the recording) every card of the task -
// each letter that went, newest first, and the draft with its Send - stood in one stack at the chat's foot, then jumped up into the turns
// that wrote them. Until the list is read nothing can be placed, so nothing is; nor under a turn at work, which holds its own cards back.
export const placesLoose = (list) => !!list && !list.working;
export const lettersTurn = (list, items) => { const xs = items || [], i = list?.letters ? xs.findIndex((x) => x.kind === "turn" && x.id === list.letters) : -1;
  return i >= 0 && !["starting", "working"].includes(xs[i].state) && !xs.slice(i + 1).some((x) => x.kind === "line") ? xs[i].id : ""; };
// ...what a turn at work waits on HIM for, in words: the step its session is stopped at, a sign-in, a question
// ...(a question the agent asked before is no wait while it works: the recorded walk, 2026-11-12, read "Waiting for your answer" over a turn
// already at work on his answer - only a step it is stopped at, or a sign-in on the page, holds a turn at work)
export const waitingOn = (list) => (list?.permissions?.length ? "Waiting for your Allow once"
  : String(list?.asking?.request_id || "").startsWith("signin:") ? "Waiting for you to sign in" : "");

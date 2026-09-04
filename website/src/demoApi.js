// taskuary.com/demo: the real app, with nothing behind it.
//
// Not a mock-up and not a video - the same React application, the same components, the same
// screens, served as static files with its API client swapped for this. Every response comes
// from a recording of a real `taskuary --demo` instance (demoFixtures.json, dumped by
// demo_fixtures.mjs), so the shapes are ones the app actually produced rather than ones
// somebody hand-wrote and let rot.
//
// It has to be USABLE, not just visible: a demo where every click fails is a screenshot with
// extra steps. So writes are applied to the recording in memory - file a message and it moves,
// make a task and it appears, ask the assistant and it answers - and none of it survives a
// reload, which is exactly what a visitor expects of a demo.
import FIXTURES from "./demoFixtures.json";
import { track } from "./demoTrack";
import { demoTerminalRecording } from "./demoTerminal.js";
import { createDemoAssistantState, installDemoAssistantTimeline } from "./demoAssistantData.js";

export const DEMO = import.meta.env?.VITE_DEMO === "1";

const clone = (x) => JSON.parse(JSON.stringify(x ?? null));
const state = clone(FIXTURES);          // the recording, as this visitor has changed it
installDemoAssistantTimeline(state);
const scriptedAssistant = createDemoAssistantState();
scriptedAssistant.transcripts[scriptedAssistant.activeTaskId] = scriptedAssistant.messages;
let nextId = 9000;

const path = (url) => String(url || "").split("?")[0];
const query = (url) => String(url || "").includes("?") ? String(url).split("?").slice(1).join("?") : "";

// a read: the exact url, then the path alone, then a shape that will not crash a caller
const read = (url) => {
  const p = path(url);
  if (p === "/api/concierge") return clone({
    task: scriptedAssistant.task, ref: `TQ-${String(scriptedAssistant.activeTaskId).padStart(4, "0")}`,
    messages: scriptedAssistant.messages, providers: [{ pick: "demo:scripted", type: "demo", label: "Scripted demo" }],
    pick: "demo:scripted", provider: "Scripted demo", model: "", scripted: true,
  });
  if (p === "/api/funnel/pile") return clone(scriptedAssistant.pile);
  if (p === "/api/concierge/chats") return clone({ data: scriptedAssistant.chats });
  let conciergeChat = p.match(/^\/api\/concierge\/chats\/(\d+)$/);
  if (conciergeChat) {
    const taskId = Number(conciergeChat[1]);
    const chat = scriptedAssistant.chats.find((c) => c.taskId === taskId);
    return clone({ task: chat || null, messages: scriptedAssistant.transcripts[taskId] || [] });
  }
  if (state[url] !== undefined && state[url] !== null) return clone(state[url]);
  if (state[p] !== undefined && state[p] !== null) return clone(state[p]);
  let m = p.match(/^\/api\/tasks\/(\d+)\/assistant$/);
  if (m) return clone(state["/api/tasks/detail"]?.[`${m[1]}:assistant`]) || { messages: [], providers: [], session: null };
  m = p.match(/^\/api\/tasks\/(\d+)$/);
  if (m) return clone(state["/api/tasks/detail"]?.[m[1]]) || null;
  m = p.match(/^\/api\/messages\/(\d+)$/);
  if (m) return clone(state["/api/messages/one"]?.[m[1]]) || null;
  m = p.match(/^\/api\/messages\/(\d+)\/attachments$/);
  if (m) return clone(state["/api/messages/attachments"]?.[m[1]]) || { data: [] };
  m = p.match(/^\/api\/doc\/([a-z]+)$/);
  if (m) return clone(state["/api/doc"]?.[m[1]]) || { content: "" };
  m = p.match(/^\/api\/terminals\/([a-z0-9]+)\/screen$/);
  if (m) return clone(demoTerminalRecording(m[1], state));
  m = p.match(/^\/api\/terminals\/([a-z0-9]+)$/);
  if (m) return clone(state["/api/terminals/scrollback"]?.[m[1]]) || clone(demoTerminalRecording(m[1], state));
  if (p.startsWith("/api/feed")) return clone(state["/api/feed"]);
  // Hub: canonical route backed by the legacy fixture key so old recordings still load.
  if (p === "/api/hub" || p === "/api/handbook") {
    const qs = Object.fromEntries(new URLSearchParams(query(url)));
    const all = hubRows(qs.status === "removed");
    let rows = all.filter((r) => (!qs.topic || r.Topic === qs.topic) && (!qs.kind || r.Kind === qs.kind)
      && (!qs.q || `${r.Title} ${r.Body}`.toLowerCase().includes(qs.q.toLowerCase())));
    if (qs.sort === "top") rows = [...rows].sort((a, b) => (b.Score || 0) - (a.Score || 0));
    return clone({ ...hubBox(), data: rows });
  }
  m = p.match(/^\/api\/(?:hub|handbook)\/(\d+)$/);
  if (m) { const r = [...hubRows(false), ...hubRows(true)].find((x) => String(x.LoreId) === m[1]); return clone(r ? { ...r, comments: r.comments || [], votes: [] } : null); }
  if (p.startsWith("/api/tasks")) return clone(state["/api/tasks"]);
  return { data: [] };                 // an unrecorded list reads as empty, never as a crash
};

// Hub's two shelves: what is live, and what the vote (or the visitor) took off.
const hubBox = () => (state["/api/hub"] ||= state["/api/handbook"] || { topics: [], data: [], count: { posts: 0, topics: 0, comments: 0 } });
const hubRows = (removed) => { const box = hubBox(); return removed ? (box.removed ||= []) : (box.data ||= []); };

// ── the writes a visitor is invited to make ──────────────────────────────────────────────
const REPLIES = [
  "In your own Taskuary this is your CLI or your AI connector answering. Here it is a script - " +
  "but everything else on this page is the real application.",
  "I would read the thread, pull the numbers it names, and come back with the two lines that " +
  "decide it. Then you approve the reply and it goes.",
];

const feedRows = () => (state["/api/feed"]?.data) || [];
const taskRows = () => (state["/api/tasks"]?.data) || [];

const assistantBox = (taskId) => {
  const key = `${taskId}:assistant`;
  const box = state["/api/tasks/detail"][key] ||= { messages: [], providers: [], session: null };
  box.session ||= { sid: `demo${taskId}`, alive: true, provider: "Claude Code · coder (your CLI)",
    label: "Taskuary assistant", mode: "assistant", model: "", pick: "cli:coder", busy: false,
    trace: [], trace_revision: 0 };
  return box;
};

const dockTask = () => {
  const old = Object.values(state["/api/tasks/detail"] || {}).map((d) => d?.task)
    .find((t) => t?.SourceRef === "assistant:dock");
  if (old) return old;
  const id = ++nextId;
  const row = { TaskId: id, ref: `TQ-${String(id).padStart(4, "0")}`, Title: "Taskuary guide",
    Summary: "An always-available walkthrough of the Timeline, outstanding work, reviews, and agent output.",
    Kind: "general", Status: "open", Priority: "normal", Source: "assistant", SourceRef: "assistant:dock",
    CreatedAt: new Date().toISOString().slice(0, 19).replace("T", " ") };
  state["/api/tasks/detail"][id] = { task: row, ref: row.ref, messages: [], attachments: [], routes: [], comments: [], runs: [], audit: [], reviews: [], session: null };
  state["/api/tasks/detail"][`${id}:assistant`] = { messages: [], session: null,
    providers: state["/api/tasks/detail"]?.["1:assistant"]?.providers || [] };
  return row;
};

const demoReply = (taskId, asked) => {
  const task = state["/api/tasks/detail"]?.[String(taskId)]?.task;
  if (task?.SourceRef !== "assistant:dock") return REPLIES[assistantBox(taskId).messages.length % REPLIES.length];
  const attention = feedRows().find((r) => r.NeedsYou) || feedRows()[0];
  const work = taskRows().find((t) => t.Status && !["done", "dropped"].includes(t.Status));
  if (/agent|coding|output/i.test(asked) && work) {
    const ref = work.ref || `TQ-${String(work.TaskId).padStart(4, "0")}`;
    return `The freshest agent work is on [${ref}](#task=${work.TaskId}). Open it to see the live output and filed result; I would check anything marked waiting before starting more work.`;
  }
  if (/task|outstanding|stuck|quiet/i.test(asked) && work) {
    const ref = work.ref || `TQ-${String(work.TaskId).padStart(4, "0")}`;
    return `Start with [${ref}](#task=${work.TaskId}) — **${work.Title}**. It is ${work.Status || "open"}; after that, I would clear anything already waiting in Review.`;
  }
  if (attention) {
    const ref = attention.TaskId ? `[TQ-${String(attention.TaskId).padStart(4, "0")}](#task=${attention.TaskId})` : "the newest Timeline item";
    return `I’d start with ${ref}: **${attention.Subject || attention.Title || "the latest message"}**. ${attention.RouteReason || "It is the item currently marked as needing you."} Then open Review for any answer that is already drafted.`;
  }
  return "Nothing in the current Timeline is marked as needing you. I’d use this quiet window to review the active task list or ask me about recent agent output.";
};

const scriptedItemLine = (item) => {
  if (!item) return "The scripted demo pipe is clear. Nothing here connects to a mailbox, an agent, or an AI.";
  if (item.kind === "agent") return item.asking
    ? `${item.agent || "The coder"} stopped on ${item.ref} and needs one choice: ${item.preview || item.why}`
    : `${item.ref} is still with ${item.agent || "the coder"}. Nothing needs you there until it stops.`;
  if (item.kind === "review") return `${item.who || "The sender"} is waiting on \u201c${item.title}\u201d. The invented draft is ready below; approving it in this demo sends nothing.`;
  if (item.kind === "report") return `${item.title} landed normally. Open the recorded report below if you want the detail.`;
  if (item.kind === "idea") return `I would keep an eye on \u201c${item.title}\u201d. ${item.why}.`;
  if (item.kind === "fyi") return `${item.who || "Someone"} sent \u201c${item.title}\u201d. It is only an FYI; no work was started.`;
  return `${item.who || "Someone"} asked about \u201c${item.title}\u201d. ${item.why || "It is still waiting for a decision."}`;
};

const itemFromTimeline = (key) => {
  const match = /^msg:(\d+)$/.exec(String(key || ""));
  if (!match) return null;
  const row = feedRows().find((r) => String(r.MessageId) === match[1]);
  if (!row) return null;
  return {
    key, kind: row.Channel === "report" ? "report" : "fyi", lane: "fyi",
    title: row.Subject || row.Title || "Timeline item", who: row.FromName || row.FromEmail || row.SourceName,
    when: row.SentAt, why: row.RouteReason, mid: row.MessageId, tid: row.TaskId, channel: row.Channel,
    preview: row.Preview,
  };
};

const scriptedNext = (key = null, only = null) => {
  const candidates = scriptedAssistant.pile.items.filter((i) => !i.settling && i.lane !== "working"
    && (!only || only !== "mail" || (i.mid && !["report", "assistant"].includes(i.channel))));
  const item = (key ? scriptedAssistant.pile.items.find((i) => i.key === key) || itemFromTimeline(key) : null)
    || candidates.find((i) => !i.surfaced) || candidates[0] || null;
  if (item && scriptedAssistant.pile.items.includes(item)) {
    item.surfaced = true;
    item.surfaced_at = "2026-09-03 10:23:00";
    scriptedAssistant.pile.rev = `demo-assistant-${++nextId}`;
  }
  const say = scriptedItemLine(item);
  scriptedAssistant.messages.push({ id: `demo-turn-${++nextId}`, role: "assistant", text: say, card: item ? clone(item) : null, at: "2026-09-03 10:23:00" });
  return { item: clone(item), say, options: [], left: Math.max(0, candidates.length - (item ? 1 : 0)), exhausted: null, scripted: true };
};

const scriptedSay = (asked, key) => {
  const text = String(asked || "").trim();
  if (/^(next|what(?:'s| is) next|keep going)\b/i.test(text)) return scriptedNext(null, null);
  if (/\b(coder|agent|census|manager)\b/i.test(text)) return scriptedNext("agent:7", null);
  let decision = null;
  if (/\b(approve|send it|looks good)\b/i.test(text)) decision = { verb: "approve" };
  else if (/\b(later|not now)\b/i.test(text)) decision = { verb: "later" };
  else if (/\b(tomorrow|remind me tomorrow)\b/i.test(text)) decision = { verb: "skip" };
  else if (/^(done|all set|close it)\b/i.test(text)) decision = { verb: "done" };
  const current = scriptedAssistant.pile.items.find((i) => i.key === key);
  const say = decision
    ? ({ approve: "The demo will mark the invented draft handled; nothing is sent.", later: "I will move this invented item back in the demo pipe.", skip: "It will reappear tomorrow in the demo.", done: "Marked done in this temporary demo." }[decision.verb])
    : current
      ? `For this scripted example: ${scriptedItemLine(current)}`
      : "This is a scripted demo response. I would use the Timeline and task history to answer that in a real Taskuary; no AI or agent is running here.";
  scriptedAssistant.messages.push({ id: `demo-user-${++nextId}`, role: "user", text, at: "2026-09-03 10:23:00" });
  scriptedAssistant.messages.push({ id: `demo-answer-${++nextId}`, role: "assistant", text: say, at: "2026-09-03 10:23:01" });
  return { say, options: [], decision, item: null, scripted: true };
};

// Start the demo's answer OUTSIDE the mounted assistant-ui generator. If the visitor clicks
// another task, React stops listening but this timer still completes and files the reply in the
// recorded task state. Coming back therefore behaves like the desktop server instead of losing
// both the progress and the answer at navigation time.
export const startDemoAssistant = (taskId, body, emit = () => {}) => {
  const box = assistantBox(taskId);
  const asked = String(body?.text || "").trim();
  if (!asked) return Promise.reject(new Error("empty message"));
  box.messages.push({ id: `u${++nextId}`, role: "user", content: [{ type: "text", text: asked }] });
  box.session.busy = true;
  box.session.trace = [{ type: "start", session: { provider: box.session.provider } }];
  box.session.trace_revision += 1;
  emit({ type: "start", session: clone(box.session) });
  return new Promise((resolve) => {
    setTimeout(() => {
      const progress = { type: "progress", name: "text", detail: "reading the task and the thread it came from" };
      box.session.trace.push(progress); box.session.trace_revision += 1; emit(clone(progress));
      setTimeout(() => {
        const said = demoReply(taskId, asked);
        box.messages.push({ id: `a${++nextId}`, role: "assistant", content: [{ type: "text", text: said }] });
        box.session.busy = false;
        const done = { type: "done", reply: said, payload: clone(box) };
        emit(done); resolve(done);
      }, 800);
    }, 500);
  });
};

// what the visitor DID, named. Every write goes through here and the panel's reads of one
// message or one task are the only reads that mean "they opened something", so this is the
// whole of the demo's instrumentation - nothing is sprinkled through the components.
const noted = (method, p) => {
  let m;
  if (method === "get" && (m = p.match(/^\/api\/(messages|tasks)\/\d+$/))) track("row", m[1]);
  else if ((m = p.match(/^\/api\/messages\/\d+\/([a-z-]+)$/))) track("verdict", m[1]);
  else if (/\/assistant\/messages$/.test(p)) track("ask", "assistant");
  else if (/\/api\/tasks$/.test(p) && method === "post") track("verdict", "new-task");
  else if (/\/api\/board\/notes$/.test(p)) track("ask", "wall-note");
  else if (method !== "get") track("verdict", p.split("/").slice(-1)[0].slice(0, 24));
};

const write = (method, url, body) => {
  const p = path(url);
  noted(method, p);
  let m;

  if (method === "post" && p === "/api/assistant/dock/new") {
    const previous = scriptedAssistant.chats.find((c) => c.taskId === scriptedAssistant.activeTaskId);
    if (previous) previous.open = false;
    const taskId = ++nextId;
    scriptedAssistant.activeTaskId = taskId;
    scriptedAssistant.task = { TaskId: taskId, Title: "New demo chat", Kind: "general", Status: "open", Source: "assistant", SourceRef: "assistant:dock", CreatedAt: "2026-09-03 10:23:00" };
    scriptedAssistant.messages = [];
    scriptedAssistant.transcripts[taskId] = scriptedAssistant.messages;
    scriptedAssistant.chats.unshift({ taskId, title: "New demo chat", at: "2026-09-03 10:23:00", started: "2026-09-03 10:23:00", turns: 0, seen: 0, mail: 0, minutes: 0, open: true });
    for (const item of scriptedAssistant.pile.items) delete item.surfaced;
    scriptedAssistant.pile.rev = `demo-assistant-${++nextId}`;
    return { task: clone(scriptedAssistant.task), ref: `TQ-${String(taskId).padStart(4, "0")}`, created: true, scripted: true };
  }

  if (method === "post" && p === "/api/concierge/next") return scriptedNext(body?.key || null, body?.only || null);
  if (method === "post" && p === "/api/concierge/open") return scriptedNext(null, null);
  if (method === "post" && p === "/api/concierge/say") return scriptedSay(body?.text, body?.key);

  if (method === "post" && p === "/api/funnel/settle") {
    const item = scriptedAssistant.pile.items.find((i) => i.key === body?.key);
    if (item) {
      if (body?.verb === "later" || body?.verb === "skip") {
        item.surfaced = false;
        item.later = body.verb === "skip" ? "2026-09-04 07:00:00" : "2026-09-03 13:23:00";
      } else if (body?.verb === "done") {
        scriptedAssistant.pile.items = scriptedAssistant.pile.items.filter((i) => i.key !== body.key);
      } else if (body?.verb === "surfaced") item.surfaced = true;
    }
    scriptedAssistant.pile.rev = `demo-assistant-${++nextId}`;
    return { key: body?.key, verb: body?.verb, until: item?.later || null, scripted: true };
  }

  if (method === "post" && (m = p.match(/^\/api\/reviews\/(\d+)\/decide$/))) {
    const review = (state["/api/reviews"]?.data || []).find((r) => String(r.ReviewId) === m[1]);
    if (review) {
      review.Status = body?.verb === "approve" ? "sent" : body?.verb || "dismissed";
      review.FinalText = body?.final_text ?? review.DraftText;
      const row = feedRows().find((r) => Number(r.ReviewId) === Number(review.ReviewId));
      if (row) { row.ReviewStatus = review.Status; row.NeedsYou = 0; }
      scriptedAssistant.pile.items = scriptedAssistant.pile.items.filter((i) => Number(i.rid) !== Number(review.ReviewId));
      scriptedAssistant.pile.rev = `demo-assistant-${++nextId}`;
    }
    return { ok: true, status: review?.Status || "handled", demo: true };
  }

  if (method === "post" && (m = p.match(/^\/api\/reviews\/(\d+)\/draft$/))) {
    const review = (state["/api/reviews"]?.data || []).find((r) => String(r.ReviewId) === m[1]);
    const draft = review?.DraftText || "Thanks - I have this. I will confirm the remaining detail and follow up shortly.";
    if (review) review.DraftText = draft;
    return { draft, reviewId: Number(m[1]), demo: true };
  }

  if (method === "post" && (m = p.match(/^\/api\/tasks\/(\d+)\/waitroom$/))) {
    const item = scriptedAssistant.pile.items.find((i) => String(i.tid) === m[1]);
    if (item) { item.asking = false; item.lane = "working"; item.why = "the scripted agent is shown as working again"; }
    scriptedAssistant.pile.rev = `demo-assistant-${++nextId}`;
    return { ok: true, queued: true, demo: true };
  }

  if (method === "post" && p === "/api/concierge/act") {
    const item = scriptedAssistant.pile.items.find((i) => i.key === body?.key);
    if (item && body?.verb === "dismiss") scriptedAssistant.pile.items = scriptedAssistant.pile.items.filter((i) => i !== item);
    scriptedAssistant.pile.rev = `demo-assistant-${++nextId}`;
    return { ok: true, verb: body?.verb, demo: true };
  }

  if (method === "post" && (m = p.match(/^\/api\/reports\/(\d+)\/rerun$/))) {
    const item = scriptedAssistant.pile.items.find((i) => String(i.source_id) === m[1]);
    return { queued: true, sourceId: Number(m[1]), title: item?.title || "Demo report", demo: true };
  }

  if (method === "post" && (m = p.match(/^\/api\/messages\/(\d+)\/(reply|dispatch|chat|mine|not-mine)$/))) {
    const messageId = Number(m[1]);
    const verb = m[2];
    const row = feedRows().find((item) => Number(item.MessageId) === messageId);
    const item = scriptedAssistant.pile.items.find((candidate) => Number(candidate.mid) === messageId);
    if (verb === "reply") {
      let review = (state["/api/reviews"]?.data || []).find((candidate) => Number(candidate.MessageId) === messageId && candidate.Status === "pending");
      if (!review) {
        review = {
          ReviewId: ++nextId, TaskId: row?.TaskId || item?.tid || null, MessageId: messageId, RunId: null, Kind: "draft",
          DraftText: "Thanks - I have this. I will confirm the remaining detail and follow up shortly.", FinalText: null,
          Status: "pending", Reason: "Scripted demo draft", DecidedBy: null, DecidedAt: null, DecideNote: null,
          CreatedAt: "2026-09-03 10:23:00", Deliver: null, Title: row?.Title || item?.title,
          Subject: row?.Subject || item?.title, FromName: row?.FromName || item?.who, FromEmail: row?.FromEmail || null,
          SentAt: row?.SentAt || item?.when, Channel: row?.Channel || item?.channel || "email", SourceName: row?.SourceName || null,
          ConversationId: row?.ConversationId || null, Preview: row?.Preview || item?.preview || "", CanSend: true,
        };
        (state["/api/reviews"].data ||= []).unshift(review);
      }
      if (row) { row.ReviewId = review.ReviewId; row.ReviewStatus = "pending"; row.HasDraft = 1; row.NeedsYou = 1; row.Category = "review"; }
      scriptedAssistant.pile.items = scriptedAssistant.pile.items.filter((candidate) => candidate !== item);
      scriptedAssistant.pile.items.unshift({
        key: `review:${review.ReviewId}`, kind: "review", lane: "approve", title: review.Subject,
        who: review.FromName || review.FromEmail, when: review.SentAt, why: "a scripted draft is waiting for your yes",
        mid: messageId, tid: review.TaskId, ref: review.TaskId ? `TQ-${String(review.TaskId).padStart(4, "0")}` : null,
        rid: review.ReviewId, channel: review.Channel, preview: review.Preview,
      });
      scriptedAssistant.pile.rev = `demo-assistant-${++nextId}`;
      return { reviewId: review.ReviewId, draft: review.DraftText, demo: true };
    }
    if (verb === "dispatch") {
      const taskId = row?.TaskId || item?.tid || ++nextId;
      scriptedAssistant.pile.items = scriptedAssistant.pile.items.filter((candidate) => candidate !== item && candidate.key !== `agent:${taskId}`);
      scriptedAssistant.pile.items.push({ ...(item || {}), key: `agent:${taskId}`, kind: "agent", lane: "working", tid: taskId,
        ref: `TQ-${String(taskId).padStart(4, "0")}`, agent: "coder", working: "coder", asking: false,
        why: "the scripted demo shows this as handed off; no agent was started" });
      scriptedAssistant.pile.rev = `demo-assistant-${++nextId}`;
      return { taskId, ref: `TQ-${String(taskId).padStart(4, "0")}`, agent: "coder", demo: true };
    }
    if (verb === "not-mine") {
      scriptedAssistant.pile.items = scriptedAssistant.pile.items.filter((candidate) => candidate !== item);
      scriptedAssistant.pile.rev = `demo-assistant-${++nextId}`;
      return { ok: true, remembered: body?.scope || "subject", demo: true };
    }
    return { ok: true, taskId: row?.TaskId || item?.tid || 1, ref: item?.ref || null, demo: true };
  }

  if (method === "post" && p === "/api/assistant/dock") {
    const task = dockTask();
    return { task: clone(task), ref: task.ref, created: true };
  }

  if (method === "post" && p === "/api/tasks") {
    const id = ++nextId;
    const row = { TaskId: id, ref: `TQ-${String(id).padStart(4, "0")}`, Title: body?.Title || "New task",
      Summary: body?.Summary || "", Kind: body?.Kind || "general", Status: "open", Priority: "normal",
      Tags: body?.Tags || null, CreatedAt: new Date().toISOString().slice(0, 19).replace("T", " ") };
    taskRows().unshift(row);
    state["/api/tasks/detail"][id] = { task: row, ref: row.ref, messages: [], attachments: [],
      routes: [], comments: [], runs: [], audit: [], reviews: [], session: null };
    state["/api/tasks/detail"][`${id}:assistant`] = { messages: [], session: null,
      providers: state["/api/tasks/detail"]?.["1:assistant"]?.providers || [] };
    return { taskId: id, ref: row.ref };
  }

  if (method === "post" && (m = p.match(/^\/api\/tasks\/(\d+)\/continue$/))) {
    const id = Number(m[1]);
    const detail = state["/api/tasks/detail"]?.[m[1]];
    if (!detail) throw new Error("task not found");
    const report = [...(detail.comments || [])].reverse().find((c) => String(c.Body || "").startsWith("CODER REPORT"));
    const agent = detail.transcript?.agent || report?.Actor || "coder";
    const sid = `continued${id}`;
    const cwd = detail.transcript?.cwd || detail.runs?.find((r) => r.AgentName === agent)?.Cwd || "~/northwind/importers";
    const instruction = String(body?.instruction || "").trim();
    const terminal = { sid, taskId: id, agent, label: agent, cwd, alive: true,
      tail: [`Owner asked next: ${instruction}`, "Opening the saved task context and checking the current checkout…"] };
    state["/api/terminals"] ||= { data: [] };
    const terminals = state["/api/terminals"].data ||= [];
    terminals.splice(0, terminals.length, terminal, ...terminals.filter((t) => Number(t.taskId) !== id));
    detail.session = terminal;
    detail.task.Status = "in_progress";
    const row = taskRows().find((t) => Number(t.TaskId) === id);
    if (row) row.Status = "in_progress";
    return { continued: true, agent, fromSession: detail.transcript?.sid || null, session: terminal };
  }

  if ((m = p.match(/^\/api\/messages\/(\d+)\/(file|promote)$/))) {
    const row = feedRows().find((r) => String(r.MessageId) === m[1]);
    if (row) {
      row.NeedsYou = 0;
      row.RouteDecision = m[2] === "file" ? "file" : "create";
      row.RouteReason = m[2] === "file" ? "nothing to do - filed by you, in the demo"
                                        : "you promoted this into a task, in the demo";
    }
    return { ok: true, taskDeleted: m[2] === "file" };
  }

  if ((m = p.match(/^\/api\/tasks\/(\d+)\/assistant\/(messages|session)$/))) {
    const box = assistantBox(m[1]);
    if (m[2] === "session") return { ...box, providers: box.providers || [] };
    const asked = String(body?.text || "").trim();
    if (asked) {
      box.messages.push({ id: `u${++nextId}`, role: "user", content: [{ type: "text", text: asked }] });
      const said = demoReply(m[1], asked);
      box.messages.push({ id: `a${++nextId}`, role: "assistant", content: [{ type: "text", text: said }] });
      return { reply: said, ...box };
    }
    return { ...box };
  }

  // Hub: vote, comment, post, remove, restore - all on the recording, none of it kept
  if ((m = p.match(/^\/api\/(?:hub|handbook)\/(\d+)\/(vote|comment|retire|restore)$/))) {
    const live = hubRows(false), gone = hubRows(true);
    const i = live.findIndex((r) => String(r.LoreId) === m[1]), j = gone.findIndex((r) => String(r.LoreId) === m[1]);
    const row = i >= 0 ? live[i] : gone[j];
    if (!row) throw new Error("no such entry");
    if (m[2] === "vote") {
      const up = !/up=false/.test(query(url));
      const was = row.MyVote || 0, now = up ? 1 : -1;
      row.Score = (row.Score || 0) - was + now; row.MyVote = now;
      if (row.Score < 0 && i >= 0) { row.Status = "downvoted"; live.splice(i, 1); gone.unshift(row); }
      else if (row.Score >= 0 && j >= 0 && row.Status === "downvoted") { row.Status = "live"; gone.splice(j, 1); live.unshift(row); }
      return clone(row);
    }
    if (m[2] === "comment") {
      (row.comments ||= []).push({ CommentId: ++nextId, LoreId: row.LoreId, Body: body?.body || "", Author: "you",
        CreatedAt: new Date().toISOString().slice(0, 19).replace("T", " ") });
      row.Comments = row.comments.length;
      return { commentId: nextId, comments: clone(row.comments) };
    }
    if (m[2] === "retire" && i >= 0) { row.Status = "retired"; live.splice(i, 1); gone.unshift(row); return { retired: true }; }
    if (m[2] === "restore" && j >= 0) { row.Status = "live"; gone.splice(j, 1); live.unshift(row); }
    return clone(row);
  }
  if (method === "post" && (p === "/api/hub" || p === "/api/handbook")) {
    const row = { LoreId: ++nextId, Topic: (body?.topic || "general").toLowerCase().replace(/[^a-z0-9]+/g, "-"), Title: body?.title || "",
      Body: body?.body || "", Author: "you", Kind: body?.kind || "howto", TaskId: null, Score: 0, MyVote: 0, Status: "live", Comments: 0,
      CreatedAt: new Date().toISOString().slice(0, 19).replace("T", " "), UpdatedAt: new Date().toISOString().slice(0, 19).replace("T", " ") };
    hubRows(false).unshift(row);
    const box = hubBox(); box.count = { ...box.count, posts: (box.count?.posts || 0) + 1 };
    if (!(box.topics || []).some((t) => t.Topic === row.Topic)) (box.topics ||= []).push({ Topic: row.Topic, n: 1 });
    return clone(row);
  }

  if (method === "post" && p === "/api/board/notes") {
    const note = { NoteId: ++nextId, TaskId: body?.task_id ?? null, Agent: body?.agent || "you",
      Cwd: "", Kind: body?.kind || "note", Body: body?.body || "", Files: "", ReadBy: "",
      CreatedAt: new Date().toISOString().slice(0, 19).replace("T", " ") };
    (state["/api/board/notes"].data ||= []).unshift(note);
    return note;
  }

  if ((m = p.match(/^\/api\/tasks\/(\d+)$/)) && method === "patch") {
    const row = taskRows().find((t) => String(t.TaskId) === m[1]);
    if (row) Object.assign(row, body || {});
    const det = state["/api/tasks/detail"]?.[m[1]];
    if (det?.task) Object.assign(det.task, body || {});
    return { ok: true };
  }

  if (p === "/api/settings" || p.startsWith("/api/setup")) return { ok: true };

  // everything else is a door out of the demo - and there is nothing on the other side of it
  const why = /send|approve/.test(p) ? "Nothing sends from the demo — in your own Taskuary this is where you approve it and it goes."
    : /connector|tools|agents|terminals|sync|ingest/.test(p) ? "This demo has no systems behind it: nothing to connect to, and nothing to run."
    : "That one needs a Taskuary of your own — this page is a recording you can click.";
  const err = new Error(why);
  err.response = { status: 403, data: { detail: why, demo: true } };
  throw err;
};

const respond = (fn) => new Promise((resolve, reject) => {
  // a beat, so spinners and disabled states are seen working rather than skipped
  setTimeout(() => { try { resolve({ data: fn() }); } catch (e) { reject(e); } }, 90);
});

const demoApi = {
  get: (url) => respond(() => { noted("get", path(url)); return read(url); }),
  post: (url, body) => respond(() => write("post", url, body)),
  patch: (url, body) => respond(() => write("patch", url, body)),
  put: (url, body) => respond(() => write("put", url, body)),
  delete: (url) => respond(() => write("delete", url)),
  interceptors: { request: { use() {} }, response: { use() {} } },
};

export default demoApi;

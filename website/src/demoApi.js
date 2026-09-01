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

export const DEMO = import.meta.env.VITE_DEMO === "1";

const clone = (x) => JSON.parse(JSON.stringify(x ?? null));
const state = clone(FIXTURES);          // the recording, as this visitor has changed it
let nextId = 9000;

const path = (url) => String(url || "").split("?")[0];
const query = (url) => String(url || "").includes("?") ? String(url).split("?").slice(1).join("?") : "";

// a read: the exact url, then the path alone, then a shape that will not crash a caller
const read = (url) => {
  if (state[url] !== undefined && state[url] !== null) return clone(state[url]);
  const p = path(url);
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
  m = p.match(/^\/api\/terminals\/([a-z0-9]+)$/);
  if (m) return clone(state["/api/terminals/scrollback"]?.[m[1]]) || null;
  if (p.startsWith("/api/feed")) return clone(state["/api/feed"]);
  if (p.startsWith("/api/tasks")) return clone(state["/api/tasks"]);
  return { data: [] };                 // an unrecorded list reads as empty, never as a crash
};

// ── the writes a visitor is invited to make ──────────────────────────────────────────────
const REPLIES = [
  "In your own Taskuary this is your CLI or your AI connector answering. Here it is a script - " +
  "but everything else on this page is the real application.",
  "I would read the thread, pull the numbers it names, and come back with the two lines that " +
  "decide it. Then you approve the reply and it goes.",
];

const feedRows = () => (state["/api/feed"]?.data) || [];
const taskRows = () => (state["/api/tasks"]?.data) || [];

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
    const box = state["/api/tasks/detail"][`${m[1]}:assistant`] ||= { messages: [], providers: [], session: null };
    box.session = box.session || { sid: `demo${m[1]}`, alive: true, provider: "Claude Code · coder (your CLI)",
      label: "Taskuary assistant", mode: "assistant", model: "", pick: "cli:coder", busy: false };
    if (m[2] === "session") return { ...box, providers: box.providers || [] };
    const asked = String(body?.text || "").trim();
    if (asked) {
      box.messages.push({ id: `u${++nextId}`, role: "user", content: [{ type: "text", text: asked }] });
      const said = REPLIES[box.messages.length % REPLIES.length];
      box.messages.push({ id: `a${++nextId}`, role: "assistant", content: [{ type: "text", text: said }] });
      return { reply: said, ...box };
    }
    return { ...box };
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

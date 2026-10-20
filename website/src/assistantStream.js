import { record } from "./lastError.js";
import { noteWrite } from "./wrote.js";

export async function* readNdjson(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  while (true) {
    const { value, done } = await reader.read();
    pending += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = pending.split("\n");
    pending = lines.pop() || "";
    for (const line of lines) if (line.trim()) yield JSON.parse(line);
    if (done) break;
  }
  if (pending.trim()) yield JSON.parse(pending);
}

// ONE TURN READ OFF THE STREAM: every event before the answer goes to `on` (which may throw - an error event ends the turn),
// and `done` is returned the moment it lands. A Next whose rail follows it (`pile_follows`, 2026-10-20: the card first, the
// rail after) returns at once with `pileLater`, the rest of the same stream read on: the `pile` event's rail, or null when
// none comes (an error, a cut stream) - the page then loads the rail itself, as it does when nothing rides along.
// null: the stream ended without an answer.
export async function readTurn(body, on = () => {}) {
  const events = readNdjson(body);
  for (;;) {
    const { value: ev, done } = await events.next();
    if (done) return null;
    if (ev.type !== "done") { on(ev); continue; }
    if (!ev.pile_follows) return ev;
    const { pile_follows: _follows, ...answer } = ev;
    const pileLater = (async () => {
      for (;;) {
        const { value, done: over } = await events.next();
        if (over || value.type === "error") return null;
        if (value.type === "pile") return value.pile || null;
      }
    })().catch(() => null);
    return { ...answer, pileLater };
  }
}

// the static demo has no server to stream from: the same events, from a script, at reading
// speed - the chat is the thing visitors try first and it has to answer
async function* demoStream(taskId, body) {
  const { startDemoAssistant } = await import("./demoApi.js");
  const queued = [];
  let wake;
  const push = (event) => { queued.push(event); wake?.(); wake = null; };
  // Do not await this promise here. Closing this generator means the view walked away, not
  // that the task stopped; startDemoAssistant owns the background run and recorded result.
  startDemoAssistant(taskId, body, push).catch((e) => push({ type: "error", error: e.message }));
  while (true) {
    if (!queued.length) await new Promise((resolve) => { wake = resolve; });
    while (queued.length) {
      const event = queued.shift();
      yield event;
      if (event.type === "done" || event.type === "error") return;
    }
  }
}

export async function* streamAssistant(taskId, body, signal) {
  if (import.meta.env.VITE_DEMO === "1") { yield* demoStream(taskId, body); return; }
  const token = localStorage.getItem("taskuary_token");
  const response = await fetch(`/api/tasks/${taskId}/assistant/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { "X-Taskuary-Token": token } : {}) },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    let message = `Assistant request failed (${response.status})`;
    try {
      const data = await response.json();
      message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
    } catch { /* keep status */ }
    const e = new Error(message); record({ message, stack: e.stack, config: { url: `/api/tasks/${taskId}/assistant/stream` } });
    throw e;
  }
  try {
    for await (const ev of readNdjson(response.body)) {
      if (ev?.type === "error") record({ message: String(ev.error || ev.message || "the answer stopped with an error"), config: { url: `/api/tasks/${taskId}/assistant/stream` } });
      yield ev;
    }
  } finally { noteWrite(); }                      // a turn can change what the sync caption shows (wrote.js)
}

export const toolTarget = (args) => {
  if (!args || typeof args !== "object") return String(args || "");
  for (const key of ["command", "file_path", "path", "query", "url", "pattern", "description", "prompt"])
    if (args[key]) return String(args[key]);
  return Object.keys(args).length ? JSON.stringify(args) : "";
};

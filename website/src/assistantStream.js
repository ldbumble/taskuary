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
    throw new Error(message);
  }
  yield* readNdjson(response.body);
}

export const toolTarget = (args) => {
  if (!args || typeof args !== "object") return String(args || "");
  for (const key of ["command", "file_path", "path", "query", "url", "pattern", "description", "prompt"])
    if (args[key]) return String(args[key]);
  return Object.keys(args).length ? JSON.stringify(args) : "";
};

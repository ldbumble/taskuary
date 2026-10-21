// The task's checklist, one shape everywhere (PW-075/PW-077): the server stores items with stable
// ids; these helpers render GitHub task-list Markdown, parse it back, flip one box without
// touching the others, and word progress without ever calling the task done - ticking boxes is
// progress on the list, closing the task is the owner's separate decision.

export const checklistMarkdown = (items) => (items || []).map((i) => `- [${i.done ? "x" : " "}] ${i.text}`).join("\n");

export function parseChecklist(md) {
  const out = [];
  for (const line of String(md || "").split(/\r?\n/)) {
    const m = /^\s*[-*]\s+\[( |x|X)\]\s+(.*)$/.exec(line);
    if (m) out.push({ id: null, text: m[2].trim(), done: m[1].toLowerCase() === "x" });
  }
  return out;
}

export const toggleItem = (items, id) => {
  if (!(items || []).some((i) => i.id === id)) return items;
  return items.map((i) => (i.id === id ? { ...i, done: !i.done } : i));
};

// A NOTE ON ONE TO-DO (the owner, 2026-10-20): kept with the box on the server (PATCH .../checklist/<id>/note, '' takes it off), shown
// in a muted line under its words. The inline field saves on Enter or when it loses focus, and Escape leaves the note as it was.
export const noteOf = (item) => String(item?.note || "").trim();
export const notePath = (taskId, itemId) => `/api/tasks/${taskId}/checklist/${encodeURIComponent(itemId)}/note`;
export const saveNote = (api, taskId, itemId, text) => api.patch(notePath(taskId, itemId), { note: String(text || "").trim() });
export const noteKey = (e, { save, cancel }) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); save(); return true; }
  if (e.key === "Escape") { e.preventDefault(); cancel(); return true; }
  return false;
};

export function progressLine(items) {
  const n = (items || []).length;
  if (!n) return "";
  const done = items.filter((i) => i.done).length;
  return `${done} of ${n} done${done === n ? " — Mark done when it is really finished" : ""}`;
}

// A TICK SHOWN BEFORE THE SERVER ANSWERS (the task page, 2026-10-20): `ticks` is { id: done } for presses still in flight, drawn over
// the list the server last sent; a press is settled - dropped - once its answer is in, unless a newer press on that box replaced it
export const withTicks = (items, ticks = {}) => (items || []).map((i) => (i.id in ticks ? { ...i, done: ticks[i.id] } : i));
export const settleTick = (ticks, id, done) => {
  if (ticks[id] !== done) return ticks;
  const { [id]: _, ...rest } = ticks;
  return rest;
};

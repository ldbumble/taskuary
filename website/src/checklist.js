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

export function progressLine(items) {
  const n = (items || []).length;
  if (!n) return "";
  const done = items.filter((i) => i.done).length;
  return `${done} of ${n} done${done === n ? " — close the task when it is really finished" : ""}`;
}

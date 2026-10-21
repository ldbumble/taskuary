// A GENERAL AGENT'S QUESTION IS SAID ONCE ON ITS CANVAS (the owner, 2026-10-21: "general agent question should only be once on the
// canvas. No need for twice"): in the Agent work pane's answer box (AgentAsks). The answer above it carried the same question - the
// model writes it over its ask marker, and general.py adds it when it did not - so the newest answer drops it while the box shows it.
// The stored answer keeps it: a phone chat has no box, and reads the question there.
const flat = (s) => String(s || "").replace(/\s+/g, " ").trim().toLowerCase();

export function withoutAsked(messages, asking) {
  const q = flat(asking?.text);
  if (!q || !messages?.length) return messages;
  const i = messages.map((m) => m.role).lastIndexOf("assistant");
  if (i < 0) return messages;
  // a paragraph that IS the question - "Which vendor?" or "Which vendor? (Acme / Globex)" - goes; the rest of the answer stays
  const drop = (text) => String(text || "").split(/\n{2,}/).filter((p) => { const f = flat(p); return f !== q && !(f.startsWith(q) && /^\s*\(.*\)$/.test(f.slice(q.length))); }).join("\n\n");
  const m = messages[i];
  const content = (m.content || []).map((c) => (c.type === "text" ? { ...c, text: drop(c.text) } : c)).filter((c) => c.type !== "text" || c.text.trim());
  return [...messages.slice(0, i), { ...m, content }, ...messages.slice(i + 1)];
}

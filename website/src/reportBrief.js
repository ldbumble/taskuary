// A BRIEF, READ AS ONE (the owner, 2026-11-07, of the End of day checkup: "This is terrible"): the model writes it to a fixed shape
// (evening.PROMPT) - a line on any connection it could not read, two one-sentence roll-ups ("Done today: ...", "Tomorrow: ..."), then
// groups of bullets "<src mark> <status mark> Who — what — gist", then one closing sentence. As markdown that was a wall of
// double-spaced bullets with three emoji in front of each. This reads the shape back, so the card can lay it out (ReportBrief.jsx);
// a text that does not have it (no roll-up, or no group of bullets) is null, and stays markdown.
const MARKS = /^(?:[\p{Extended_Pictographic}\p{Emoji_Presentation}\uFE0F\u200D\u20E3]|\s)+/u;
const STATUS = { "✅": "done", "🔍": "next", "📅": "meeting" };
const plain = (s) => String(s || "").replace(/^\s*#{1,6}\s+/, "").replace(/^\*\*(.*)\*\*:?$/, "$1").replace(/^__(.*)__:?$/, "$1").replace(/:\s*$/, "").trim();
const ROLLUP = /^\s*(?:\*\*|__)?([A-Z][\w' ]{1,24}?)(?::(?:\*\*|__)|(?:\*\*|__)?:)\s*(.+)$/;
const BULLET = /^\s*(?:[-*•]|\d+[.)])\s+(.*)$/;
// the server's own first line when a connection could not be read (reports.py unread_line): a note above the brief, never a roll-up
const UNREAD = /^Not read this run:/;

// one bullet: its marks (the source's own, then done / next / meeting) and its words split on the dashes, at most three parts
export function briefItem(line) {
  const t = String(line || "").trim(), lead = (MARKS.exec(t) || [""])[0];
  const marks = [...lead.replace(/\s+/g, "")].reduce((a, ch) => (/[\uFE0F\u200D\u20E3]/.test(ch) && a.length ? [...a.slice(0, -1), a[a.length - 1] + ch] : [...a, ch]), []);
  const status = marks.map((m) => STATUS[m.replace(/\uFE0F/g, "")]).filter(Boolean), src = marks.find((m) => !STATUS[m.replace(/\uFE0F/g, "")]) || "";
  const parts = t.slice(lead.length).split(/\s+[—–]\s+/).map((p) => p.trim()).filter(Boolean);
  const [who, what, ...gist] = parts.length > 2 ? parts : parts.length === 2 ? [parts[0], "", parts[1]] : ["", "", parts[0] || ""];
  return { src, status, who, what, gist: gist.join(" — "), text: t.slice(lead.length).trim() };
}

export function briefOf(text) {
  const lines = String(text || "").split(/\r?\n/), out = { notes: [], rollups: [], groups: [], closing: [] };
  let group = null, pending = null;
  for (const raw of lines) {
    const l = raw.trim(); if (!l) continue;
    const b = BULLET.exec(l);
    if (b) { if (!group) { group = { title: pending ? plain(pending) : "", items: [] }; out.groups.push(group); pending = null; } group.items.push(briefItem(b[1])); continue; }
    if (pending) out[out.groups.length ? "closing" : "notes"].push(plain(pending));
    if (UNREAD.test(l)) { out.notes.push(l); pending = null; continue; }
    const r = !out.groups.length && ROLLUP.exec(l);
    if (r && !/^https?$/i.test(r[1])) { out.rollups.push([r[1].trim(), r[2].replace(/\*\*$/, "").trim()]); pending = null; continue; }
    group = null; pending = l;
  }
  if (pending) out[out.groups.length ? "closing" : "notes"].push(plain(pending));
  return out.rollups.length && out.groups.length ? out : null;
}

// Triage's reading of a task's thread (triage.thread_of): {asking, your_part, others:[{who,did}], asks:[{mid,about}], aside:[{mid,why}], on_you:[str]}.
// Optional on a verdict - older ones, CLI brains and an edited TRIAGE.md lack it - so anything partial reads as less, never as an error.
const str = (v) => (typeof v === "string" ? v.trim() : "");
const arr = (v) => (Array.isArray(v) ? v : []);
export function readingOf(raw) {
  let r = raw;
  if (typeof r === "string") { try { r = JSON.parse(r); } catch { return null; } }
  if (!r || typeof r !== "object" || Array.isArray(r) || !(str(r.asking) || str(r.your_part))) return null;
  return { asking: str(r.asking), your_part: str(r.your_part), others: arr(r.others).filter((o) => o && typeof o === "object"),
    asks: arr(r.asks).filter((o) => o && typeof o === "object"), aside: arr(r.aside).filter((o) => o && typeof o === "object" && str(o.why)),
    on_you: arr(r.on_you).map(str).filter(Boolean) };
}
// ...and on an item no task holds (a report, an FYI, a dashboard: ItemSections' middle): what it says and what matters to you, no more
export const itemLines = (r) => (r ? [{ k: "says", text: r.asking }, { k: "matters", text: r.your_part }].filter((l) => l.text) : []);
const mday = (at) => { const m = /(\d{4})-(\d{2})-(\d{2})/.exec(String(at || "")); return m ? `${+m[2]}/${+m[3]}` : ""; };
export function readingLines(r, mails = []) {
  if (!r) return [];
  const by = new Map((mails || []).map((m) => [String(m.MessageId), m])), out = [];
  const ask = [...r.asks].reverse().map((a) => by.get(String(a.mid))).find(Boolean);   // the newest ask is the one the reply answers
  if (r.asking) out.push({ k: "ask", text: r.asking });
  if (r.your_part) out.push({ k: "part", text: r.your_part });
  const oth = r.others.map((o) => [str(o.who), str(o.did)].filter(Boolean).join(" ")).filter(Boolean);
  if (oth.length) out.push({ k: "others", text: oth.join("; ") });
  const whys = new Map();
  for (const a of r.aside) whys.set(str(a.why), (whys.get(str(a.why)) || 0) + 1);
  const to = ask ? ` the reply answers ${[ask.FromName && `${ask.FromName}'s`, mday(ask.SentAt) && `${mday(ask.SentAt)} email`].filter(Boolean).join(" ") || "the newest ask"}` : "";
  for (const [why, n] of whys) out.push({ k: "aside", text: `${n} ${n === 1 ? "email is" : "emails are"} ${why}${to ? `, so${to}` : ""}` });
  for (const t of r.on_you) out.push({ k: "onyou", text: t });
  return out;
}

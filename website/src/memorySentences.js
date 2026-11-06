// THE MEMORY PAGE READS AS SENTENCES (the owner, 2026-11-06): LEARNED.md stays the store, but the page shows each learned line as one
// plain sentence with Keep / Wrong / Forget - never the file with its [s:N | ev | seen | k] tags. The graph (/api/learned/graph)
// already parses the tags off; this strips whatever else a line can carry (a date stamp, a [memory:key], markdown) and says, faintly,
// when it was learned and from what. Pure, so node --test reads it.
import { fmtDate } from "./dates.js";

export const sentence = (t) => {
  let s = String(t || "")
    .replace(/^\s*[-*]\s+/, "")                                   // a list bullet
    .replace(/^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?:\s*/, "")   // a date stamp the pass wrote first
    .replace(/\s*\[(?:s:\d+|memory:|k:|ev:)[^\]]*\]/g, "")       // a tag the parser left (an older line's, or one inline)
    .replace(/<!--[\s\S]*?-->/g, "")                              // a comment marker
    .replace(/\*\*([^*]+)\*\*|__([^_]+)__/g, "$1$2").replace(/`([^`]+)`/g, "$1")
    .replace(/\s+/g, " ").trim();
  if (!s) return "";
  s = s[0].toUpperCase() + s.slice(1);
  return /[.!?…)"']$/.test(s) ? s : `${s}.`;
};

// what a line was learned FROM, in the owner's words - by the kind of evidence most of it is (learnedgraph._resolve)
const FROM = { verdict: "your verdicts", review: "your reviews", task: "what you did on tasks", message: "mail you answered",
  deferred: "tasks you put off", promise: "your sent mail", idea: "the Advisor's ideas", outcome: "how things turned out", press: "your presses" };
export const fromWhere = (evs = []) => {
  const n = {};
  for (const e of evs) { const w = FROM[e?.kind]; if (w) n[w] = (n[w] || 0) + 1; }
  const ws = Object.entries(n).sort((a, b) => b[1] - a[1]).map(([w]) => w);
  return ws.length > 2 ? `${ws[0]}, ${ws[1]} and more` : ws.join(" and ");
};
const day = (d) => { const t = new Date(String(d || "").replace(" ", "T")); return Number.isFinite(+t) ? fmtDate(t, undefined, { month: "short", day: "numeric" }) : ""; };
// "learned Oct 3 from your verdicts" - the first evidence's date, else when it was last seen; "you wrote this" for the owner's own line
export const provenance = (l) => {
  if (!l) return "";
  if (l.own) return "you wrote this";
  const first = (l.evidence || []).map((e) => e?.date).filter(Boolean).sort()[0] || l.seen, when = day(first), where = fromWhere(l.evidence);
  return when || where ? ["learned", when, where && `from ${where}`].filter(Boolean).join(" ") : "";
};

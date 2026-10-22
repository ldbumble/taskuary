// What the Agent work card draws from a session record (taskuary/sessionrecord.py) - kept out of the component so the
// one rule that matters is testable: the result is said ONCE (the owner, 2026-10-10: "make sure it's full and complete
// record but don't duplicate sections").

import { plural } from "./timeWords.js";

const norm = (s) => String(s || "").replace(/\s+/g, " ").trim();
// markdown's marks off a line shown as plain text (a folded summary, an earlier session's one line)
export const plain = (s) => String(s || "").replace(/^\s*(#+|>)\s*/gm, "").replace(/[*\x60]/g, "").trim();

// the steps the full record lists. A conversation's own turns are already on screen in the chat under the card, so for a
// general session only its WORKING is listed (thoughts, tools, plans, errors); and the step that is the result itself
// becomes a pointer back to it rather than a second copy.
export const recordSteps = (s) => {
  const chat = s?.source === "conversation", res = norm(s?.result);
  return (s?.steps || [])
    .filter((x) => !(chat && (x.k === "you" || x.k === "said")))
    .map((x) => (x.k === "said" && res && norm(x.text) === res ? { ...x, k: "result" } : x));
};

// THE CARD'S ORDER (the owner, 2026-10-10: "decided/changed/summary ... should go first no, then full summary then files it
// wrote/every step"): what happened leads - the report's summary, else the first paragraph of the agent's own last words -
// with Decided and Changed as rows under it; then the last message, without whatever the lead already said.
export const cardParts = (s, draft) => {
  const r = s?.report || {}, res = String(s?.result || "").trim(), paras = res.split(/\n\s*\n/);
  const lead = norm(r.summary) ? String(r.summary).trim() : paras[0] || "";
  let message = norm(r.summary) ? res : paras.slice(1).join("\n\n").trim();
  if (norm(message) === norm(lead)) message = "";
  const rows = [["Decided", r.decided], ["Changed", r.changed]].filter(([, v]) => norm(v) && norm(v) !== norm(res));
  // the last message is often the agent's own account of its work, and sometimes the reply it drafted: it is called the
  // reply only when the draft on the task is IN it, never on a guess
  const d = norm(draft).slice(0, 160);
  return { lead, rows, message, isReply: !!(d && norm(res).includes(d)) };
};

// the files it saved in the project it worked in, as paths inside it; everything else (scratch, temp, notes) is counted apart
export const splitFiles = (files, cwd) => {
  const slash = (p) => String(p || "").replace(/\\/g, "/").replace(/\/+$/, "");
  const root = slash(cwd).toLowerCase(), mine = [], other = [];
  for (const f of files || []) {
    const p = slash(f);
    if (root && p.toLowerCase().startsWith(root + "/")) mine.push(p.slice(root.length + 1)); else other.push(p);
  }
  return { mine, other };
};

// one line of facts: who, when, and how much it did - each only when there is some (its files are under What it made)
export const recordFacts = (s) => {
  const c = s?.counts || {};
  return [s?.cli || s?.by, s?.at && s.at.slice(0, 16),
    c.thought ? plural(c.thought, "thought") : "", c.tool ? plural(c.tool, "step") : ""].filter(Boolean);
};

// is there anything behind "Every step" that the card does not already show?
export const hasMore = (s) => !!(recordSteps(s).some((x) => x.k !== "result") || s?.plan?.length || s?.refused?.length);

// WHAT THE ONE "MORE" HOLDS, named on the button: everything past what happened - its last message in full, the files, the
// run's timeline, what ended it since, every step, earlier sessions. One control, so nothing is drawn twice and nothing is
// a second section (the owner, 2026-10-12: "main summary, then details behind more").
export const moreParts = (s, { draft = "", timeline = [], since = null, earlier = 0 } = {}) => {
  const steps = recordSteps(s).filter((x) => x.k !== "result").length, files = s?.files?.length || 0;
  return [cardParts(s, draft).message && "its last message", files && plural(files, "file"), timeline?.length && "the timeline",
    since?.text && "since then", (steps || s?.plan?.length) && (s?.source === "conversation" ? "its working" : plural(steps, "step")),
    s?.refused?.length && plural(s.refused.length, "refusal"), earlier && plural(earlier, "earlier session")].filter(Boolean);
};

// the state line over the record: the story's sentence, else - nothing being left to do - what ended it upstream, which is
// then not repeated as "since then"
export const recordHead = (story, ended) => story?.line ? { state: story, since: ended?.text ? ended : null }
  : ended?.text ? { state: { kind: "ended", line: ended.text }, since: null } : { state: null, since: null };

const SOURCES = { conversation: "the conversation", screen: "what was on screen" };
export const sourceLabel = (src) => SOURCES[src] || src || "";

// A RUN BY ITS LAST WORDS (the owner, 2026-10-15: "main thing is the last summary message from each model run"): its last message,
// without the prompt box a screen-read log carries along with it ("▌▌ Work in a new folder..."), else its written summary
// ...the last thing it SAID first: `result` is every message of the run strung together, and showed the whole run as its "last" one
const isSaid = (x) => x.k === "said" && String(x.text || "").trim();
// ...but a line it said and then WORKED PAST is progress, not its last words (2026-10-18: a run that ended by filing its reply
// through a tool led with "Next I'm checking the run log" - its written result never repeated that line, so it is the answer)
export const lastWords = (s) => {
  const st = s?.steps || [], i = st.findLastIndex(isSaid), said = i < 0 ? "" : String(st[i].text).trim();
  const res = String(s?.result || "").split("\n").filter((l) => !/^\s*▌/.test(l)).join("\n").trim();
  const workedPast = i >= 0 && st.slice(i + 1).some((x) => x.k === "tool"), stem = norm(said).replace(/…$/, "");
  if (said && workedPast && res && !norm(res).includes(stem)) return res;
  return said || res || String(s?.report?.summary || "").trim();
};
// every run, newest first, numbered from the first: Run 3 · latest, Run 2, Run 1
// ...each by ITS OWN steps: runs that resumed one CLI conversation share its log, so every run's record carried all of it and Run 2
// said Run 3's last words (2026-10-15). A run's `at` is when it ended: its steps are the ones after the run before it ended.
const when = (t) => Date.parse(String(t || "").replace(" ", "T"));
export const runsOf = (sessions) => (sessions || []).map((s, i, all) => {
  const end = when(s.at), after = i + 1 < all.length ? when(all[i + 1].at) : -Infinity;
  const timed = (s.steps || []).length && (s.steps || []).every((x) => !Number.isNaN(when(x.at)));
  // the session's written result is the NEWEST run's: an older run sharing its log is cut to its own steps without it
  const own = timed && !Number.isNaN(end) ? { ...s, steps: s.steps.filter((x) => when(x.at) > after && when(x.at) <= end + 60_000), result: i ? "" : s.result } : s;
  return { s, n: all.length - i, said: lastWords(own) };
});

// THE RESULT, WHEN AN AGENT HAS STOPPED AND SAVED (the task page redesign, owner-approved 2026-10-21): what it found, how it resolved it,
// and the whole summary of its write-up - the saved report, never a raw log. Each part only where the write-up recorded it; its last
// words are said once, and not where they only repeat the summary or a row.
export const resultParts = (s) => {
  const r = s?.report || {}, said = String(lastWords(s) || "").trim();
  const rows = [["What it found", r.decided], ["How it resolved it", r.changed]].filter(([, v]) => norm(v)).map(([k, v]) => [k, String(v).trim()]);
  const summary = norm(r.summary) ? String(r.summary).trim() : "";
  const writeup = said && norm(said) !== norm(summary) && !rows.some(([, v]) => norm(v) === norm(said)) ? said : "";
  return { rows, summary, writeup };
};
// a unified diff counted - how many files, lines added and removed - from the run's own DiffText, never a git call
export const diffStat = (text) => {
  const ls = String(text || "").split(/\r?\n/), files = new Set();
  for (const l of ls) if ((l.startsWith("+++ ") || l.startsWith("--- ")) && !/\/dev\/null$/.test(l)) files.add(l.slice(4).replace(/^[ab]\//, "").trim());
  const added = ls.filter((l) => l.startsWith("+") && !l.startsWith("+++")).length, removed = ls.filter((l) => l.startsWith("-") && !l.startsWith("---")).length;
  return files.size || added || removed ? { files: files.size, added, removed } : null;
};

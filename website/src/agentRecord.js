// What the Agent work card draws from a session record (taskuary/sessionrecord.py) - kept out of the component so the
// one rule that matters is testable: the result is said ONCE (the owner, 2026-10-10: "make sure it's full and complete
// record but don't duplicate sections").

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

const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

// one line of facts: who, when, and how much it did - each only when there is some (its files are under What it made)
export const recordFacts = (s) => {
  const c = s?.counts || {};
  return [s?.cli || s?.by, s?.at && s.at.slice(0, 16),
    c.thought ? plural(c.thought, "thought") : "", c.tool ? plural(c.tool, "step") : ""].filter(Boolean);
};

// is there anything behind "Every step" that the card does not already show?
export const hasMore = (s) => !!(recordSteps(s).some((x) => x.k !== "result") || s?.plan?.length);

// WHAT THE ONE "MORE" HOLDS, named on the button: everything past what happened - its last message in full, the files, the
// run's timeline, what ended it since, every step, earlier sessions. One control, so nothing is drawn twice and nothing is
// a second section (the owner, 2026-10-12: "main summary, then details behind more").
export const moreParts = (s, { draft = "", timeline = [], since = null, earlier = 0 } = {}) => {
  const steps = recordSteps(s).filter((x) => x.k !== "result").length, files = s?.files?.length || 0;
  return [cardParts(s, draft).message && "its last message", files && plural(files, "file"), timeline?.length && "the timeline",
    since?.text && "since then", (steps || s?.plan?.length) && (s?.source === "conversation" ? "its working" : plural(steps, "step")),
    earlier && plural(earlier, "earlier session")].filter(Boolean);
};

// the state line over the record: the story's sentence, else - nothing being left to do - what ended it upstream, which is
// then not repeated as "since then"
export const recordHead = (story, ended) => story?.line ? { state: story, since: ended?.text ? ended : null }
  : ended?.text ? { state: { kind: "ended", line: ended.text }, since: null } : { state: null, since: null };

const SOURCES = { conversation: "the conversation", screen: "what was on screen" };
export const sourceLabel = (src) => SOURCES[src] || src || "";

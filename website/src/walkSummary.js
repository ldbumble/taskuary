// The start of the walk: what is waiting, before the first card (the owner, 2026-09-23). It replaces the Morning digest
// as the day's opener. IT IS THE RAIL (the owner, 2026-10-02: "it should just read from the rail no?"): the same bands in
// the same order with the same names - its own who-wants-what grouping put a finished agent's task under "Agents
// waiting" while the rail had it On you, and no agent was working on it.
import { LEVEL_ORDER, SECTION_WORDS, bandsOf, levelOf } from "./funnelPile.js";
import { isAgentKind, onYou } from "./lanes.js";

export const GROUPS = LEVEL_ORDER.map((key) => ({ key, word: SECTION_WORDS[key] }));
export const groupOf = (i) => levelOf(i);
const AGENT_LANES = new Set(["blocked", "stopped", "saved", "queued", "working", "broken", "unjudged"]);
// ...an agent's own kind of row is lanes.json's `agent` (a proposed action carries the agent that drafted it)
const isAgentRow = (i) => !!i?.agent && (AGENT_LANES.has(i.lane) || isAgentKind(i.kind));

// HOW A ROW READS IS THE SERVER'S (funnel_presentation.shows): who asks - the person, the agent on an agent's row, the
// service behind a service's mail, "Report" for a report - and the one state word under it. This file had its own copy
// and the phone another; the 2026-10-13 "why does fyi say my name??" fix reached only this one. Every card the page
// gets went through funnel.present, which sets `shows`; the plain field is all that is left for a card without it.
export const whoOf = (i) => i?.shows?.who || String(i?.who || i?.agent || "").trim() || "someone";

// the task number a row belongs to, "" for one with no task yet
export const refOf = (i) => i?.ref || (i?.tid ? `TQ-${String(i.tid).padStart(4, "0")}` : "");

// the one line under a row's "who" - the server's word, else the lane's
export const stateOf = (i, laneWord) => i?.shows?.state || laneWord;

// a band's card says who it is from, never what each one said - the rail beside it has the rows (the owner, 2026-10-06)
// ...a report has no "who" but its own name, so it says that
// ...and an agent's row says the TASK, not the profile running it: a profile name alone read as a task of that name (the owner, 2026-10-08)
const cut = (t, n = 40) => t.length <= n ? t : `${t.slice(0, n).replace(/\s+\S*$/, "")}…`;
// ...nor a row with nobody behind it but the agent - a task an agent opened from a report, say - whose only name IS the profile
// ...and an agent's FINISHED work (kind agentdone), whose "who" is the agent itself with no agent field beside it (TQ-1016 live)
const byAgent = (i) => isAgentRow(i) || i?.kind === "agentdone"
  || (!!i?.agent && (!String(i?.who || "").trim() || String(i.who).trim().toLowerCase() === String(i.agent).toLowerCase()));
const gistWord = (i) => whoOf(i) === "Report" ? String(i.title || "").split(/ [-—] /)[0]
  : byAgent(i) && i.title ? cut(String(i.title).trim()) : whoOf(i);
export const gistOf = (g, max = 2) => {
  const ws = [...new Set(g.rows.map(gistWord))].filter(Boolean);
  return ws.slice(0, max).join(", ") + (ws.length > max ? ` +${ws.length - max}` : "");
};

export function summarize(items) {
  // the same sender saying the same thing twice is one row with a count - two identical lines read as a glitch
  const fold = (rows) => rows.reduce((out, i) => {
    const twin = !refOf(i) && out.find((o) => !refOf(o) && whoOf(o) === whoOf(i) && o.title === i.title);
    if (twin) twin.count = (twin.count || 1) + 1; else out.push({ ...i });
    return out;
  }, []);
  // the band's count is the RAIL's count (every row), the rows under it fold twins; `you` is how many of them are on you (lanes.onYou)
  const groups = bandsOf(items).map((b) => ({ key: b.level, word: SECTION_WORDS[b.level], n: b.items.length, rows: fold(b.items),
    you: b.items.filter((i) => onYou(i, b.level)).length }));
  const n = groups.reduce((t, g) => t + g.n, 0);
  const lead = n
    ? `${n} thing${n === 1 ? "" : "s"}: ${groups.map((g) => `${g.n} ${g.key === "fyi" ? g.word : g.word.toLowerCase()}`).join(", ")}.`
    : "Nothing is waiting on you.";
  return { n, groups, lead };
}

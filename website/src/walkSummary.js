// The start of the walk: what is waiting, before the first card (the owner, 2026-09-23). It replaces the Morning digest
// as the day's opener. IT IS THE RAIL (the owner, 2026-10-02: "it should just read from the rail no?"): the same bands in
// the same order with the same names - its own who-wants-what grouping put a finished agent's task under "Agents
// waiting" while the rail had it On you, and no agent was working on it.
import { LEVEL_ORDER, SECTION_WORDS, bandsOf, levelOf } from "./funnelPile.js";

export const GROUPS = LEVEL_ORDER.map((key) => ({ key, word: SECTION_WORDS[key] }));
export const groupOf = (i) => levelOf(i);
const AGENT_LANES = new Set(["blocked", "stopped", "saved", "queued", "working", "broken", "unjudged"]);

// who asks: the person or the agent - and for a report, whose sender IS its title, the word "Report"
// An agent's row names the AGENT - the task's "who" was the owner who started it, and "You" under Agents waiting
// said nothing (the owner, 2026-09-30). An address shows its name part: "securityapp", not "noreply-securityapp@...".
const isAgentRow = (i) => !!i?.agent && (AGENT_LANES.has(i.lane) || ["agent", "agentdone", "action"].includes(i.kind));
const person = (w) => w.includes("@") ? w.split("@")[0].replace(/^no-?reply[-._]?/i, "") || w.split("@")[0] : w;
export const whoOf = (i) => {
  const who = person(String((isAgentRow(i) ? i.agent : i?.who || i?.agent) || "").trim()), title = String(i?.title || "");
  if (who && !title.toLowerCase().startsWith(who.toLowerCase().slice(0, 16))) return who;
  return i?.kind === "report" || i?.lane === "report" ? "Report" : who || "someone";
};

// the task number a row belongs to, "" for one with no task yet
export const refOf = (i) => i?.ref || (i?.tid ? `TQ-${String(i.tid).padStart(4, "0")}` : "");

// the one line under a row's "who": the lane's word, except a drafted reply, which is the thing to approve
export const stateOf = (i, laneWord) => i?.lane === "approve"
  ? (i.kind === "action" && !i.closeout ? "wants a yes" : laneWord) : laneWord;   // a reply and a close-out: the lane's one word

// a band's card says who it is from, never what each one said - the rail beside it has the rows (the owner, 2026-10-06)
// ...a report has no "who" but its own name, so it says that
export const gistOf = (g, max = 2) => {
  const ws = [...new Set(g.rows.map((i) => whoOf(i) === "Report" ? String(i.title || "").split(/ [-—] /)[0] : whoOf(i)))].filter(Boolean);
  return ws.slice(0, max).join(", ") + (ws.length > max ? ` +${ws.length - max}` : "");
};

export function summarize(items) {
  // the same sender saying the same thing twice is one row with a count - two identical lines read as a glitch
  const fold = (rows) => rows.reduce((out, i) => {
    const twin = !refOf(i) && out.find((o) => !refOf(o) && whoOf(o) === whoOf(i) && o.title === i.title);
    if (twin) twin.count = (twin.count || 1) + 1; else out.push({ ...i });
    return out;
  }, []);
  // the band's count is the RAIL's count (every row), the rows under it fold twins
  const groups = bandsOf(items).map((b) => ({ key: b.level, word: SECTION_WORDS[b.level], n: b.items.length, rows: fold(b.items) }));
  const n = groups.reduce((t, g) => t + g.n, 0);
  const lead = n
    ? `${n} thing${n === 1 ? "" : "s"}: ${groups.map((g) => `${g.n} ${g.key === "fyi" ? g.word : g.word.toLowerCase()}`).join(", ")}.`
    : "Nothing is waiting on you.";
  return { n, groups, lead };
}

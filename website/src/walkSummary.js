// The start of the walk: who wants what, before the first card (the owner, 2026-09-23: "summary of who
// wants what task (or list of tasks that we created for ourselves), agent actions, and pending reply so
// we just approve"). It replaces the Morning digest as the day's opener. A pure GROUPING of lanes the
// pile already carries - nothing is judged here, and the rail's own split is untouched.
export const GROUPS = [
  { key: "people", word: "People want" },
  { key: "you", word: "You wanted" },
  { key: "agents", word: "Agents waiting" },
  { key: "read", word: "Nothing to decide" },
];

const AGENT_LANES = new Set(["blocked", "stopped", "queued", "working", "broken", "unjudged"]);
const READ_LANES = new Set(["report", "fyi"]);

export const groupOf = (i) => {
  if (!i) return "read";
  if (i.kind === "action" || i.kind === "agent" || i.kind === "agentdone" || AGENT_LANES.has(i.lane)) return "agents";
  if (READ_LANES.has(i.lane) || ["fyis", "report", "idea", "wrapup"].includes(i.kind)) return "read";
  if (i.kind === "todo" || i.channel === "own") return "you";
  return "people";
};

// who asks: the person or the agent - and for a report, whose sender IS its title, the word "Report"
export const whoOf = (i) => {
  const who = String(i?.who || i?.agent || "").trim(), title = String(i?.title || "");
  if (who && !title.toLowerCase().startsWith(who.toLowerCase().slice(0, 16))) return who;
  return i?.kind === "report" || i?.lane === "report" ? "Report" : who || "someone";
};

// the one line under a row's "who": the lane's word, except a drafted reply, which is the thing to approve
export const stateOf = (i, laneWord) => i?.lane === "approve" ? (i.kind === "action" ? "wants a yes" : "draft ready") : laneWord;

export function summarize(items) {
  const live = (items || []).filter((i) => i && i.lane !== "working");
  const groups = GROUPS.map((g) => ({ ...g, rows: live.filter((i) => groupOf(i) === g.key) })).filter((g) => g.rows.length);
  const ready = live.filter((i) => i.lane === "approve").length;
  const skip = live.filter((i) => groupOf(i) === "read").length;
  const yours = live.filter((i) => groupOf(i) === "you").length;
  const word = live.length - ready - skip - yours;
  const n = (k, one, many) => `${k} ${k === 1 ? one : many}`;
  const parts = [ready && `${n(ready, "is", "are")} ready - you only approve`, word && `${n(word, "needs", "need")} a word`,
                 yours && `${yours} ${yours === 1 ? "is" : "are"} on your list`, skip && `${skip} you can skip`].filter(Boolean);
  const lead = live.length
    ? `${live.length} thing${live.length === 1 ? "" : "s"}. ${parts.join(", ").replace(/^./, (c) => c.toUpperCase())}.`
    : "Nothing is waiting on you.";
  return { n: live.length, groups, lead };
}

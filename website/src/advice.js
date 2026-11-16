// The filled button of the item on the table (spec 2026-10-12; the task's own recommended move since 2026-11-09, never the Advisor's since
// 2026-11-15): the pure piece, so it can be tested without a browser. The rest is wiring in AssistantView.jsx: it lights a button on the row
// (ActionRow) - no line stands over the row (2026-10-26), and no Advisor section in the task (2026-11-05).

/* WHEN THE STRIP SPEAKS (the owner, 2026-10-13: "there should not be an updated advisor comment when it's refreshing ... not while
   waiting or walking through things"). Only the decision read for the item on the table NOW - a line read for the item before it stood
   over the next one until the new read came back - and only while nothing is in flight. THE OBVIOUS MOVE IS SILENT (the owner,
   2026-10-23): a decision lights its verb with `line` '' - the strip says nothing and the button does the talking. An agent at work is
   nothing for the owner to do: whatever was read before it started, its decision is Next, said by nothing. */
export function adviceShown(advice, item, busy) {
  if (!advice?.verb || busy || !item?.key || advice.for !== item.key) return null;
  return item.lane === "working" ? { ...advice, verb: "next", line: "", state: "working" } : advice;
}

/* WHAT THE STRIP SAYS AND WHAT THE ROW LIGHTS, ONE DECISION (the UI audit's C2, 2026-10-21; the design's phase A, 2026-10-23): the
   one decision (rulebook.decide) is what every surface lights; an answer with no verb (a key nothing is decided on, an idea row, an agent
   at work) lights Next and says nothing - and no missing AI lights its Connect (the owner, 2026-11-15: "the agent should suggest").
   `shown`/`lit`: the decision and the Assistant's light, already read for the item on the table. */
export function stripWord({ speaks, busy, shown = null, lit = null, advice = null, key = "", lane = "" } = {}) {
  const working = lane === "working", mine = !!advice && advice.for === key;
  const quiet = !!speaks && !busy && !lit && !shown && ((mine && !!advice.none) || working) ? { verb: "next", line: "", for: key } : null;
  return { pick: lit || shown || quiet };
}

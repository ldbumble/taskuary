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
   one decision (rulebook.decide) is what every surface lights. Only one reason for lighting nothing is said - no AI connected, where the
   move needs one (`needs_ai`) - with its way out lit; any other answer with no verb (a key nothing is decided on, an idea row) lights Next
   and says nothing. An agent at work outranks a missing AI.
   `shown`/`lit`: the decision and the Assistant's light, already read for the item on the table; `aiOff`: caps.ai === false. */
export function stripWord({ speaks, busy, shown = null, lit = null, aiOff = false, advice = null, key = "", lane = "" } = {}) {
  const working = lane === "working", mine = !!advice && advice.for === key;
  const noAi = !!speaks && !busy && !lit && !working && mine && (advice.none === "no_ai" || (aiOff && !!advice.needs_ai));
  const quiet = !!speaks && !busy && !lit && !noAi && !shown && ((mine && !!advice.none) || working) ? { verb: "next", line: "", for: key } : null;
  return { noAi, pick: lit || (noAi ? { none: "no_ai", for: key } : shown || quiet) };
}

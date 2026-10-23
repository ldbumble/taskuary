// The Advisor's line on the item on the table (spec 2026-10-12, build step 3): the pure piece, so it can be tested without a
// browser. The rest is wiring in AssistantView.jsx; it is drawn at the canvas foot (ActionRow.AdvisorNext), not in the prompt box.

/* Which key to re-read advice for when an `advice` live event lands: the event carries the target's legacy key
   (task:N / msg:N) while the table holds the rail's key (processing:... in a real install) - a card's aliases bridge
   the two. Returns the table's key, or null when the event is about something else. */
import { sameTarget } from "./tableState.js";
export function adviceKeyFor(ev, cur) {
  const k = ev?.key;
  if (!k || !cur) return null;
  if (typeof cur === "string") return k === cur ? cur : null;
  if (!cur.key) return null;
  return k === cur.key || (cur.aliases || []).includes(k) || sameTarget(ev, cur) ? cur.key : null;
}

/* The suggestion as the strip says it: the Advisor's sentence without its verb in front ("Reply: Gail is asking..." -> "Gail is
   asking...") - the filled button below already names the move (the owner, 2026-10-13: "it should not say NEXT Reply - just give
   suggestion"). Only a lead-in that IS the move's own word goes; any other sentence is kept whole. */
export function suggestion(line, label, verb) {
  const l = String(line || "").trim();
  const names = [label, verb, String(verb || "").replace(/_/g, " ")].filter(Boolean).map((w) => String(w).trim().toLowerCase());
  const m = l.match(/^["“]?([^:"”]{1,40}?)["”]?\s*(?::|\s[-–—]|\s+because\b)\s*(.+)$/i);
  if (!m || !names.includes(m[1].trim().toLowerCase())) return l;
  return m[2].charAt(0).toUpperCase() + m[2].slice(1);
}

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
   Advisor's one decision (advisor.decide) is what every surface lights. Only one reason for lighting nothing is said - no AI connected,
   where the move needs one (`needs_ai`, or the server's {none: "no_ai"}) - with its way out lit; any other answer with no verb (a key
   nothing is decided on, the Advisor switched off) lights Next and says nothing. An agent at work outranks a missing AI.
   `shown`/`lit`: the Advisor's decision and the Assistant's light, already read for the item on the table; `aiOff`: caps.ai === false. */
export function stripWord({ speaks, busy, shown = null, lit = null, aiOff = false, advice = null, key = "", lane = "" } = {}) {
  const working = lane === "working", mine = !!advice && advice.for === key;
  const noAi = !!speaks && !busy && !lit && !working && mine && (advice.none === "no_ai" || (aiOff && !!advice.needs_ai));
  const quiet = !!speaks && !busy && !lit && !noAi && !shown && ((mine && !!advice.none) || working) ? { verb: "next", line: "", for: key } : null;
  return { noAi, pick: lit || (noAi ? { none: "no_ai", for: key } : shown || quiet) };
}

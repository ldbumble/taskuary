// The Advisor's line in the prompt box (spec 2026-10-12, build step 3): the two pure pieces, so they can be tested
// without a browser. The rest is wiring in AssistantView.jsx.

/* Which key to re-read advice for when an `advice` live event lands: the event carries the target's legacy key
   (task:N / msg:N) while the table holds the rail's key (processing:... in a real install) - a card's aliases bridge
   the two. Returns the table's key, or null when the event is about something else. */
export function adviceKeyFor(ev, cur) {
  const k = ev?.key;
  if (!k || !cur) return null;
  if (typeof cur === "string") return k === cur ? cur : null;
  if (!cur.key) return null;
  return k === cur.key || (cur.aliases || []).includes(k) ? cur.key : null;
}

export const GHOST_TAIL = "Tell me what to do with it, or press…";
const GHOST_CAP = 90;

/* The ghost text: the Advisor's line, capped so its tail - the part that points at the pill - stays visible in a
   one-row box (the long hint was cut mid-word on the phone, 2026-09-20), then the way to answer. The phone keeps its
   own short hint and lets the pill alone carry the line. */
export function ghostText(line, phone) {
  const l = String(line || "").trim();
  if (!l || phone) return null;
  const cut = l.length > GHOST_CAP ? `${l.slice(0, GHOST_CAP - 1).trimEnd()}…` : l;
  return `${cut} ${GHOST_TAIL}`;
}

// The Advisor's line on the item on the table (spec 2026-10-12, build step 3): the pure piece, so it can be tested without a
// browser. The rest is wiring in AssistantView.jsx; it is drawn at the canvas foot (ActionRow.AdvisorNext), not in the prompt box.

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

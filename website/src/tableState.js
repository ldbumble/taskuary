// ONE RECORD OF WHAT IS ON THE TABLE (general fix 4, 2026-10-18): the item, its key, whether its view is folded or a page is open
// over it, and whether the Advisor may speak for it. The strip, the rail ring, the box's words and the Advisor each worked it out on
// their own, so a folded task kept its Advisor strip and its dark button acting on what nobody could see (re-audit item 4).
import { foldsAs } from "./funnelPile.js";

export function tableOf({ current = null, cardKey = null, foldedKey = null, browsing = null, setup = false } = {}) {
  const key = current || cardKey || null;
  const folded = foldsAs(foldedKey, key), place = !!browsing;
  return { key, folded, place, speaks: !!key && !folded && !place && !setup };
}

// What an /api/advice answer (advisor.status) means for the strip: a line, "Thinking..." only while a judgement is really in
// flight, or nothing. It spun 20 s and then showed nothing over items the Advisor never judges (error sweep, 2026-10-18).
// `cap` is the one reason said aloud; the rest are the item's own business (an agent at work, a report that ran fine).
export function adviceRead(data, key) {
  if (!data || !key) return { advice: null, asking: null };
  if (data.verb || data.none === "no_ai" || data.none === "cap") return { advice: { ...data, for: key }, asking: null };
  return { advice: null, asking: data.pending ? key : null };
}
export const CAP_LINE = "No suggestion for a while - the Advisor has read as many items as it may this hour.";

// THE ADVISOR'S EVENT NAMES ITS ITEM BY THE RAIL'S KEY, and a task opened by name sits on the table as `task:N` - so the line for a
// Board-opened task landed and was never read (re-audit: "a task opened by name never gets its Advisor line"). The event's own
// target says which task it is.
export function sameTarget(ev, cur) {
  const m = /^task:(\d+)$/.exec(cur?.key || "");
  const tid = m ? Number(m[1]) : cur?.tid;
  return ev?.target_kind === "task" && tid != null && Number(ev.target_id) === Number(tid);
}

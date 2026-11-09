// ONE RECORD OF WHAT IS ON THE TABLE (general fix 4, 2026-10-18): the item, its key, whether its view is folded or a page is open
// over it, and whether the Advisor may speak for it. The strip, the rail ring, the box's words and the Advisor each worked it out on
// their own, so a folded task kept its Advisor strip and its dark button acting on what nobody could see (re-audit item 4).
import { foldsAs } from "./funnelPile.js";
import { ASK_ASSISTANT } from "./kinds.js";

// ...SETUP IS QUIET ONLY WHILE IT IS IN VIEW: a task opened over it by its link or by Search (`over`, AssistantView's setupCard) is the
// item in front of the owner, and it drew its row with nothing lit and no line while the same task in the walk had both (the memory
// A/B's UI pass, 2026-10-26: "make the opened task get its advice too")
export function tableOf({ current = null, cardKey = null, foldedKey = null, browsing = null, setup = false, over = false } = {}) {
  const key = current || cardKey || null;
  const folded = foldsAs(foldedKey, key), place = !!browsing;
  return { key, folded, place, speaks: !!key && !folded && !place && (!setup || !!over) };
}

// SOMETHING IS OPEN OVER THE CHAT: an item on the table in view (not folded by its X) or a page. Then the Assistant's own icons (read
// aloud, Past chats, New chat) live in its corner pill, where over a task they cannot read as the task's (2026-11-06); with nothing open
// the canvas IS the Assistant's chat, and they sit in its head again - the owner could not find New chat there ("there used to be button
// to clear the chat??", 2026-11-06)
export const overChat = (t) => !!t?.place || (!!t?.key && !t?.folded);

// WHAT THE RAIL'S TAG AND THE BOX SAY of it (the 2026-10-19 UI walk, G5): a page opened over the item keeps it on the table - its ringed
// row still brings it back - but it is not in view, and "on the table" and "Ask about this one" said it was while Connections covered it
// ...and the next ask is about THE PAGE ALONE (the owner, 2026-11-05): it no longer carries the task beneath, so the box names only the page
export function tableWords(table, ref = "") {
  const has = !!table?.key, under = has && !!table.place;
  return { box: !has ? "Ask Taskuary anything — a name or a subject pulls it in…"
      : under ? "Ask about this page…" : "Ask about this one, tell me what to do with it, or name something else…",
    // ...the corner pill is the Assistant (the owner, 2026-11-06): it brings you around; the task's own agent has the task's box
    phone: !has ? "Ask Taskuary anything…" : under ? "Ask about this page…" : ASK_ASSISTANT,
    // ...and the one-row bar's pill, whose words ("Ask…") name no task: its name for a reader and the walk says which
    // one the chat will talk about, with no visible change (the dead-end walk's RING, 2026-10-27)
    name: !has ? "Ask Taskuary anything" : under ? "Ask Taskuary about this page" : `Tell Taskuary what to do with ${ref || "this one"}` };
}

// What an /api/advice answer (advisor.status) means for the strip: the Advisor's ONE decision - a lit verb, its line '' when the move is
// obvious - or why nothing is lit. There is no "Thinking..." any more (the owner, 2026-10-23): the rule's button is lit at once, and
// the model's answer, where it reads one, arrives by the `advice` event. A decision that lights nothing (an agent asking) is kept too.
export function adviceRead(data, key) {
  if (!data || !key) return { advice: null };
  return { advice: data.verb || data.none || data.state ? { ...data, for: key } : null };
}

// THE ADVISOR'S EVENT NAMES ITS ITEM BY THE RAIL'S KEY, and a task opened by name sits on the table as `task:N` - so the line for a
// Board-opened task landed and was never read (re-audit: "a task opened by name never gets its Advisor line"). The event's own
// target says which task it is.
export function sameTarget(ev, cur) {
  const m = /^task:(\d+)$/.exec(cur?.key || "");
  const tid = m ? Number(m[1]) : cur?.tid;
  return ev?.target_kind === "task" && tid != null && Number(ev.target_id) === Number(tid);
}

// THE TASK YOU WERE WORKING ON (the owner, 2026-11-09: "there should always be a button on top corner when you are in settings or reports to
// go back to the main task you were working on"): the last task in view, however it came - the walk, the rail, a link, the Board or an
// answer's "Open TQ-0005" (the owner, 2026-11-09: "any task you are on then switch to settings is [the] task")
export const workedOn = (table, item) => {
  const tid = Number(item?.tid) || 0;
  if (!table?.key || table.folded || table.place || !tid) return null;
  return { key: table.key, tid, ref: item.ref || `TQ-${String(tid).padStart(4, "0")}`, title: item.title || "" };
};
// ...and the corner offers the way back while something else is in front of it: a page, or another task. On that task itself, no Back
export const backToWork = (table, worked, tid = 0) =>
  !!worked && (!!table?.place || (!!table?.key && !table.folded && Number(tid) !== worked.tid));
export const workWords = (w, n = 28) => {
  const t = (w?.title || "").trim();
  return `Back to ${w.ref}${t ? ` ${t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t}` : ""}`;
};

// ONE RECORD OF WHAT IS ON THE TABLE (general fix 4, 2026-10-18): the item, its key, whether its view is folded or a page is open
// over it, and whether the Advisor may speak for it. The strip, the rail ring, the box's words and the Advisor each worked it out on
// their own, so a folded task kept its Advisor strip and its dark button acting on what nobody could see (re-audit item 4).
import { foldsAs } from "./funnelPile.js";
import { ASK_ASSISTANT, ASSISTANT_NAME } from "./kinds.js";
import { unlitWhy } from "./railStatus.js";

// ...SETUP IS QUIET ONLY WHILE IT IS IN VIEW: a task opened over it by its link or by Search (`over`, AssistantView's setupCard) is the
// item in front of the owner, and it drew its row with nothing lit and no line while the same task in the walk had both (the memory
// A/B's UI pass, 2026-10-26: "make the opened task get its advice too")
// ...AND WITH NOTHING PUT ON IT, THE CARD THE CHAT DRAWS LIVE (`drawn`, funnelPile.drawnKey - walk 11): after a restart the record was empty while
// the chat's newest task card drew live, so the task stood inside the home with the home's own box under its own and the home's icons in its head
export function tableOf({ current = null, cardKey = null, drawn = null, foldedKey = null, browsing = null, setup = false, over = false } = {}) {
  const key = current || cardKey || drawn || null;
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
  return { box: !has ? `Ask ${ASSISTANT_NAME} — a name or a subject pulls it in…`
      : under ? "Ask about this page…" : "Ask about this one, tell me what to do with it, or name something else…",
    // ...the corner pill is the Assistant (the owner, 2026-11-06): it brings you around; the task's own agent has the task's box
    phone: !has ? ASK_ASSISTANT : under ? "Ask about this page…" : ASK_ASSISTANT,
    // ...and the one-row bar's pill, whose words ("Ask…") name no task: its name for a reader and the walk says which
    // one the chat will talk about, with no visible change (the dead-end walk's RING, 2026-10-27)
    name: !has ? `Ask ${ASSISTANT_NAME}` : under ? `Ask ${ASSISTANT_NAME} about this page` : `Tell ${ASSISTANT_NAME} what to do with ${ref || "this one"}` };
}

// What a decision (rulebook.status's shape) means for the strip: ONE decision - a lit verb, its line '' when the move is obvious - or why
// nothing is lit. There is no "Thinking..." (the owner, 2026-10-23): the button is lit at once. A decision that lights nothing is kept too.
export function adviceRead(data, key) {
  if (!data || !key) return { advice: null };
  return { advice: data.verb || data.none || data.state ? { ...data, for: key } : null };
}

// ONLY AN IDEA ROW IS THE ADVISOR'S (the owner, 2026-11-09: "assistant/advisor should only be on rail"): every other row fills the task's own
// recommended move, served with the task and with the rail's item (`recommended`: { verb, label, why, state } or null) - no model, no ask
// ...known BY ITS ITEM, not its key: the rail hands every row a key of its own (processing:pi_...), an idea among them, and by the key alone
// the Advisor's row read as a task's - nothing asked, nothing lit. A bare key is an idea only where it says so (idea:4, opened by name)
export const isIdea = (o) => (o && typeof o === "object" ? o.kind === "idea" || isIdea(o.key) : /^idea:/.test(String(o || "")));
export const ownPick = (rec, key) => (rec?.verb && key
  ? { verb: rec.verb, label: rec.label || "", state: rec.state || "", why: rec.why || "", line: "", by: "agent", for: key, key }
  // ...and with nothing lit, the state's own sentence alone (railStatus.unlitWhy): no verb, so nothing is filled - the row says it
  : unlitWhy(rec) && key ? { verb: "", label: "", state: rec.state || "", why: unlitWhy(rec), line: "", by: "agent", for: key, key } : null);


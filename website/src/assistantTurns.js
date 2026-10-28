// Reconcile optimistic chat bubbles with the durable turns returned by the server.
// Local bubbles use a/u/r/context ids; persisted comments use their database id. Comparing only
// ids drew both copies after every freshness read even though the server had recorded one turn.
import { label as btn } from "./buttons.js";

const optimistic = (m) => typeof m?.id === "string" && /^(?:a|u|r|context)\d+$/.test(m.id);
const words = (v) => String(v || "").replace(/\s+/g, " ").trim();
// a receipt drawn at the click is the server's recorded line, come back as an assistant turn - the
// same words, so it is the same turn (a card-carrying line is its own). A failure's line is
// recorded with its way on as a words card (concierge.receipt_turn): read as its own turn, every failed or
// stale press showed its receipt twice (re-audit, 2026-10-18)
// ...and two lines carrying two different ITEMS are two turns, whatever their words: on the desk an item comes up under a few words
// that name only its kind ("Next up: a report."), so three reports in a row said the same thing - the second's durable turn was taken
// for the first's bubble, its card replaced the first's in place and the walk's line of the report it left was gone (CI's RECEIPT,
// 2026-10-21)
const cardOf = (m) => (m?.card?.key && !NOT_ITEM.has(m.card.kind) ? m.card.key : "");
const sameTurn = (a, b) => (a?.role === b?.role || (a?.role === "receipt" && b?.role === "assistant" && (!b?.card || b.card.kind === "words")))
  && words(a?.text) === words(b?.text) && (!cardOf(a) || !cardOf(b) || cardOf(a) === cardOf(b));

export function mergeDurableTurns(local = [], durable = []) {
  const messages = [...local];
  // A reconciled bubble answers to BOTH names: the optimistic id it is keyed by on screen, and the
  // comment id the server gave it. Tracking only the visible one made every freshness read re-match
  // a turn that had already been reconciled.
  const ids = new Set(messages.flatMap((m) => [m.id, m.commentId, ...(m.alias || [])]).filter((v) => v != null));
  const claimed = new Set();
  const added = [];
  for (const turn of durable || []) {
    if (ids.has(turn.id)) {
      // ...except the day's opener, which the server draws at once and fills in its place when the mail is in (welcome.arrive):
      // skipped by id, its counts stayed "reading" until a reload
      const at = turn.card?.kind === "brief" ? messages.findIndex((m) => m.id === turn.id || m.commentId === turn.id) : -1;
      if (at >= 0 && JSON.stringify(messages[at].card) !== JSON.stringify(turn.card)) messages[at] = { ...messages[at], text: turn.text, card: turn.card };
      // ...and a press the server stamped on a line already drawn (concierge._stamp_pressed): its badge, at once
      const was = turn.card?.pressed ? messages.findIndex((m) => m.id === turn.id || m.commentId === turn.id) : -1;
      if (was >= 0 && !messages[was].pressed) messages[was] = { ...messages[was], pressed: turn.card.pressed, ...(turn.card.pressed_note ? { pressedNote: turn.card.pressed_note } : {}) };
      continue;
    }
    const at = messages.findIndex((candidate, i) => !claimed.has(i) && optimistic(candidate) && sameTurn(candidate, turn));
    if (at >= 0) {
      // KEEP THE BUBBLE'S OWN ID. AssistantView keys the chat by it, so swapping it for the comment
      // id unmounted the line and mounted a fresh one in its place - destroying and rebuilding the
      // card inside it. That is the blink every message did a moment after it was sent (the owner,
      // 2026-09-04: "appears, flickers and reapears"). The durable id rides along instead, so the
      // next read still recognises the turn and skips it.
      const bubble = messages[at];
      // ...and its proposal: the durable turn has none, and without it the card lost its buttons and
      // was redrawn as the item (the owner, 2026-09-07: "shows it then reshows it")
      // ...and its words: the durable turn is text only, so an answer lost the item's verbs - Next with them -
      // the moment the server's copy came back (2026-09-23: ask a question, and there is no way on)
      // ...and its `done`: a card put down at the press is the page's own fact, the durable turn never carries it, and
      // dropping it drew the batch just read live again (the owner, 2026-10-02: "it reopens the same 4 again")
      // ...and its ALIASES (G8, 2026-10-20): the lines of the same item it replaced (placeLine) are its names too. Dropped here, the
      // next read found the oldest of them unknown, pushed it at the end, and oneCopy kept that copy - the item the walk had left
      // came back live on the table, under a rail ringing the new one, until the next press
      // ...and a send's fold (`sent`, AssistantView sent): its Mark done and Next stay on the row, not only Next
      messages[at] = { ...turn, id: bubble.id, commentId: turn.id, ...(bubble.done ? { done: true } : {}), ...(bubble.pressed ? { pressed: bubble.pressed } : {}), ...(bubble.pressedNote ? { pressedNote: bubble.pressedNote } : {}), ...(bubble.alias?.length ? { alias: bubble.alias } : {}),
                       ...(bubble.sent ? { sent: true } : {}),
                       ...(bubble.proposal ? { proposal: bubble.proposal, card: bubble.card } : {}),
                       ...(bubble.chips?.length && !turn.chips?.length ? { chips: bubble.chips } : {}),
                       // ...and its status: the durable turn has none, and an error receipt lost its "Report this bug" with it
                       ...(bubble.role === "receipt" ? { role: "receipt", tid: bubble.tid, ref: bubble.ref, chips: bubble.chips,
                                                         ...(bubble.status ? { status: bubble.status } : {}) } : {}) };
      claimed.add(at);
    } else {
      messages.push(turn);
      added.push(turn);
    }
    ids.add(turn.id);
  }
  return { messages: oneCopy(messages), added };
}

// ONE COPY OF AN ITEM IN THE CHAT (the 2026-10-19 UI walk: TQ-0010 stood five times, once per search, Board or rail pick): an item
// opened again moves its line to the end - folded there as the walk's record, live there when it is the table - never a second line.
// The copies it replaces stay its aliases, so a later read of the server's history does not bring them back.
const NOT_ITEM = new Set(["proposal", "words", "brief", "setup", "walk", "firstrun", "setup_questions"]);
// ...and a line Next drew ahead of its answer (AssistantView surface) is no copy yet: the answer replaces it or takes it down, so an older
// line's ids folded into it here would go down with it
export const itemKey = (m) => (m?.role === "assistant" && m.card?.key && !m.proposal && !m.ahead && !NOT_ITEM.has(m.card.kind) ? m.card.key : "");
const ids = (m) => [m.id, m.commentId, ...(m.alias || [])].filter((v) => v != null);
export function placeLine(messages = [], line) {
  const key = itemKey(line);
  const at = key ? messages.map(itemKey).lastIndexOf(key) : -1;
  if (at < 0) return [...messages, line];
  const old = messages[at];
  return [...messages.slice(0, at), ...messages.slice(at + 1), { ...line, alias: [...new Set([...ids(old).filter((v) => v !== line.id), ...(line.alias || [])])] }];
}
// ...and the owner's pick of it ("Show me ..." from the rail) is said once too: picking between two rows added another line per pick, the
// same title twice and more (verify, 2026-10-19). The pick is the page's own line - the server never records it - so the last stands
export const pickLine = (messages = [], line) => (line?.pick ? [...messages.filter((m) => !(m.role === "user" && m.pick === line.pick)), line] : [...messages, line]);
export function oneCopy(messages = []) {
  const keys = messages.map(itemKey), all = keys.filter(Boolean);
  if (new Set(all).size === all.length) return messages;
  const ms = [...messages];
  ms.forEach((m, i) => { const last = keys[i] ? keys.lastIndexOf(keys[i]) : i; if (last !== i) ms[last] = { ...ms[last], alias: [...new Set([...(ms[last].alias || []), ...ids(m)])] }; });
  return ms.filter((m, i) => !keys[i] || keys.lastIndexOf(keys[i]) === i);
}

// A PRESS IS A BADGE ON ITS CARD, NEVER A LINE (the owner, 2026-10-22: "why do we have done-mark done text. we don't need that text ever. I
// hate free text" ... "put a little animation on the corner of the past task - like button marked done not free text"): the newest line
// carrying the item gets the button's own label. Nothing found, nothing changes - and still no line.
const holds = (m, it) => !!m?.card && m.role === "assistant" && !m.proposal && !NOT_ITEM.has(m.card.kind)
  && ((!!it?.key && m.card.key === it.key) || (it?.tid != null && it.tid !== "" && String(m.card.tid ?? "") === String(it.tid)));
// ...but THE CHAT POP-UP HAS NO CARD TO WEAR THE BADGE (the owner, 2026-10-27: it "disappeared when done", and Show the last answer was
// "useless"): a turn that only lit or pressed left the owner's own line alone in it. Its receipt says what was done and where, read off the
// act's own result - the server's line when it gave one - one sentence for every act, never one per verb. {text, status} for a receipt line
export function actReceipt(data = {}, tableKey = null) {
  const act = data.pressed || data.light || null;
  const where = !act ? "" : act.key && act.key === tableKey ? "this task" : act.ref || "this task";
  const said = String(act?.line || data.receipt || "").trim();
  if (said) return { text: said, status: data.pressed ? "done" : "warn" };
  if (!act) return { text: "No answer came back on that - nothing was changed.", status: "warn" };
  if (!act.label) return { text: `Brought up ${where}.`, status: "warn" };
  return data.pressed ? { text: `${act.label} - ${where}${act.note ? `: ${act.note}` : ""}.`, status: "done" }
    : { text: `${act.label} is ready on the row for ${where} - yours to press.`, status: "warn" };
}
// ...and a Close with a note carries its note (`note`), drawn after the badge (the owner, 2026-10-23: "write on it marked done with note")
export function pressLine(messages = [], it, label, note = "") {
  if (!label) return messages;
  const at = messages.map((m) => holds(m, it)).lastIndexOf(true);
  return at < 0 ? messages : messages.map((m, i) => (i === at ? { ...m, pressed: label, ...(note ? { pressedNote: note } : {}) } : m));
}
// ...and a word pressed under a line (a send's Mark done, a Not ours taken further) marks THAT line, and leaves it, so it is not pressed twice
const sameChip = (a, b) => a?.verb === b?.verb && a?.label === b?.label && (a?.tid ?? null) === (b?.tid ?? null);
const chipsHeld = (m) => m?.chips || m?.card?.chips || [];
export function pressChip(messages = [], chip) {
  const at = messages.map((m) => chipsHeld(m).some((c) => sameChip(c, chip))).lastIndexOf(true);
  return at < 0 ? messages : messages.map((m, i) => (i === at ? { ...m, pressed: chip.label, chips: chipsHeld(m).filter((c) => !sameChip(c, chip)) } : m));
}
// the badge's label: the page's own at the press, the server's stamp after a read
export const pressedOf = (m) => m?.pressed || m?.card?.pressed || "";
export const pressedNoteOf = (m) => m?.pressedNote || m?.card?.pressed_note || "";
// NEXT'S BADGE says what Next did to the card it left (the owner, 2026-10-23: "should show read on reports if you go pass them when you hit
// next"): "Read" on a row Next settles read - a report, a dashboard, an agent's finished result, an fyi - and "Next" on one it only passes,
// still yours. The server's next_badge (concierge.py) is the same rule, so the stamp a reload reads says the same word.
// ...a report that failed is in the broken lane, and read all the same: it has no task to stay on
const READ_ON_NEXT = new Set(["report", "fyi"]);
const readOnNext = (c) => READ_ON_NEXT.has(c?.lane) || (c?.kind === "report" && !c?.tid);
export const nextBadge = (card) => btn("next", card?.kind === "fyis" ? "batch" : readOnNext(card) ? "read" : undefined);

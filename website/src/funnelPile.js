import vocab from "../../taskuary/lanes.json" with { type: "json" };
import { label } from "./buttons.js";
import { says, subState } from "./laneSays.js";
import { ago, band } from "./timeWords.js";
import { fmtDateTime } from "./dates.js";
import { LEVEL_META, LEVEL_ORDER, SECTION_WORDS, attentionBand, isUrgent, levelOf, onYou } from "./lanes.js";
export { says, subState };
// the rail's sections and the on-you rule are lanes.js's, re-exported where the rail's readers have always found them
export { LEVEL_META, LEVEL_ORDER, SECTION_WORDS, attentionBand, isUrgent, levelOf, onYou };
// The pipe, as the Assistant page draws it: what each lane is called and coloured, which item is a
// new arrival (it drops in from the top and slides to its slot), and which card goes under a line.
// Pure and dependency-free so it runs under bare node (test/funnelPile.test.mjs); colour is named
// by ROLE (theme.jsx ROLES) so this file cannot drift from the palette.

// ONE VOCABULARY, in taskuary/lanes.json - loaded by the chat (funnel.py) from the same file, so a
// lane cannot mean one thing on the rail and another in a sentence. They were two hand-kept tables
// in two languages and had already drifted: this page said a report lane reads "report" while the
// server said "landed", and nothing could tell you which was the mistake (the owner, 2026-09-15:
// "we built one idea and then it was changed... it's in a bunch of places").
//
// The file carries word, role (theme.jsx ROLES, or null for a lane that takes no colour), mark, hint,
// and `loud` on the one lane that is a person waving at you from across the room - the only lane where
// work has actually STOPPED until you answer. `counted` is the plural-counting form ("3 landed", never
// "3 report") and defaults to the word.
const byKey = (rows) => Object.fromEntries(rows.map(({ key, counted, ...meta }) => [key, meta]));
export const LANES = vocab.lanes.map((l) => l.key);
export const LANE_META = byKey(vocab.lanes);
// the word that COUNTS, for a sentence that says how many of each are waiting
export const LANE_COUNTED = Object.fromEntries(vocab.lanes.map((l) => [l.key, l.counted || l.word]));
export const laneCounted = (lane) => LANE_COUNTED[lane] || LANE_COUNTED.fyi;
export const laneMeta = (lane) => LANE_META[lane] || LANE_META.fyi;

// A few KINDS carry more than their lane does. An agent's finished job and a report you set up share
// the 'report' lane (both just landed), but reading "report" on the agent's own summary is wrong (the
// owner, 2026-09-03: "it's not a report but agent awaiting little hand no?").
export const KIND_META = byKey(vocab.kinds);
export const STATE_META = byKey(vocab.states);
// A TASK'S STATE (taskstate.py, T1-T9): a lane where the rail has one, else a state (theirs, closed) or a kind (agentdone)
// - every word the Tasks list and the Board draw comes from lanes.json
export const taskStateMeta = (key) => LANE_META[key] || STATE_META[key] || KIND_META[key] || null;
// ...and a reply the server refused (funnel: `not_sent`) wears "not sent" in red, never the lane's "ready to send" (the UI audit, 2026-10-21)
export const rowMeta = (item) => ({ ...laneMeta(item?.lane), ...(KIND_META[item?.kind] || {}), ...(item?.not_sent ? KIND_META.not_sent : {}) });

// The column is drawn top → bottom = next out → last out: the SERVER sends next-first and the rail
// keeps that order, so what triage moved up is what you see first (it used to be drawn upside down,
// mouth at the bottom of a funnel; the owner, 2026-09-03: "everything comes out from the top").
export const drawOrder = (items) => [...(items || [])];

// Which keys just LEFT: drawn last time, gone now - they fall out of the mouth
export const departures = (prevItems, items) => {
  if (!prevItems) return [];
  const now = keysOf(items);
  return prevItems.filter((i) => !now.has(i.key));
};

// Which keys just landed: in the new pile, not in the last one we drew. The first paint is not an
// arrival - forty items dropping in at once on page load is a fireworks display, not a pipe.
export const arrivals = (prevKeys, items) => {
  if (!prevKeys) return new Set();
  return new Set((items || []).map((i) => i.key).filter((k) => !prevKeys.has(k)));
};
export const keysOf = (items) => new Set((items || []).map((i) => i.key));

// ``rev`` is retained by the server for older clients, but it only described membership/lane.
// New responses carry a full display revision, including complete cards and backing content.
// Keeping this fallback lets the static demo and an older server continue to paint normally.
export const displayRevision = (pile) => pile?.display_revision || pile?.rev || null;
export const refreshPilePresentation = (current, fresh) => {
  // AN OLDER ANSWER NEVER UNDOES A NEWER ONE (the owner, 2026-09-28: "read agents working for a split second into your
  // task, then goes back"): a poll and a turn's answer race, and whichever landed last was drawn - a build from before
  // the agent spoke put its row back where it had been for a frame
  if (current && Number(fresh?.generated_at) < Number(current?.generated_at)) return current;
  const revision = displayRevision(fresh);
  if (!(current && revision && displayRevision(current) === revision)) return fresh;
  // Selection capture is intentionally separate from the completed display revision. A transient
  // unavailable result can therefore recover with the same rows/revision, and a newly captured
  // token must still replace the disabled or older marker.
  const membersMatch = Array.isArray(current.expected_next_members)
    && Array.isArray(fresh.expected_next_members)
    && current.expected_next_members.length === fresh.expected_next_members.length
    && current.expected_next_members.every((member, index) => member === fresh.expected_next_members[index]);
  const selectionMatches = current.selection_unavailable === fresh.selection_unavailable
    && current.selection_invalidated === fresh.selection_invalidated
    && current.selection_revision === fresh.selection_revision
    && current.expected_next_key === fresh.expected_next_key
    && (current.expected_next_members === undefined && fresh.expected_next_members === undefined || membersMatch);
  return selectionMatches ? current : fresh;
};

// A completed pile response captures the server's exact automatic selection.  Keep the scope
// beside the token in the browser: a token for "all except A" cannot authorize a mail-only walk,
// nor can it authorize moving on after Current has changed to B.
export const nextSelectionScope = (only = null, exclude = null, includeSurfaced = false) => ({
  only: only || null,
  include_surfaced: !!includeSurfaced,
  exclude: exclude || null,
});
export const sameSelectionScope = (left, right) => !!left && !!right
  && left.only === right.only
  && left.include_surfaced === right.include_surfaced
  && left.exclude === right.exclude;
export const hasNextSelection = (pile) => !!pile
  && (pile.selection_unavailable === true || pile.selection_invalidated === true
    || (typeof pile.selection_revision === "string"
    && Object.prototype.hasOwnProperty.call(pile, "expected_next_key")
    && Array.isArray(pile.expected_next_members)));
export const captureNextSelection = (pile, scope) => hasNextSelection(pile)
  && !pile.selection_unavailable && !pile.selection_invalidated ? {
  selection_revision: pile.selection_revision,
  expected_next_key: pile.expected_next_key ?? null,
  expected_next_members: [...pile.expected_next_members],
  selection_pending: pile.selection_pending ?? null,
  scope: nextSelectionScope(scope?.only, scope?.exclude, scope?.include_surfaced),
} : null;
export const nextSelectionBody = (capture) => ({
  selection_revision: capture.selection_revision,
  expected_next_key: capture.expected_next_key,
  expected_next_members: [...capture.expected_next_members],
  only: capture.scope.only,
  include_surfaced: capture.scope.include_surfaced,
  exclude: capture.scope.exclude,
});
// THE TABLE MOVED AND NO RAIL CAME WITH IT (a row clicked, a task pulled by name): the selection the rail holds was captured for the
// table as it was, so its NEXT ring named the row the walk would have taken from THERE - the top of the rail, over the row just put on
// the table - until the reload landed, and a press read in that gap disagreed with the ring (PW-118, CI 2026-10-22). Withdraw the
// marker until the read for the new table lands; the reload's fresh selection replaces it (refreshPilePresentation).
export const withdrawSelection = (pile) => pile && hasNextSelection(pile) && !pile.selection_unavailable ? {
  ...pile, selection_invalidated: true, expected_next_key: null, expected_next_members: [],
} : pile;
export const nextMarkerKey = (pile, items, current) => {
  if (hasNextSelection(pile))
    return pile.expected_next_members[0] || pile.expected_next_key || null;
  // ...a task an agent is working included: the walk takes every task in the rail's order (the owner, 2026-10-21)
  // ...an urgent row too, in its place (the owner, 2026-10-22: "you go through it like all other tasks")
  const eligible = (item) => !item.settling && item.key !== current?.key;
  return ((items || []).find((item) => eligible(item) && !item.surfaced)
    || (items || []).find(eligible))?.key || null;
};
export const canAdvanceSelection = (pile, ready, only = null) => {
  if (!hasNextSelection(pile)) return (ready || []).length > 0;
  if (pile.selection_unavailable || pile.selection_invalidated) return false;
  if (pile.expected_next_key) return true;
  // (a mail-only walk used to continue here; the mode is gone - 2026-09-25, no typed word picks a walk)
  return false;
};

// Both an initial HTTP conflict and a late streamed conflict carry this shape.  Keeping parsing
// here lets the UI share one no-retry path and avoids rendering a structured `detail` object.
export const selectionGuardDetail = (error) => {
  const detail = error?.detail || error?.response?.data?.detail;
  if (detail?.code === "selection_unavailable") return detail;
  return detail?.code === "selection_stale" ? detail : null;
};
export const replaceSelectionToken = (pile, detail) => pile ? (detail.code === "selection_unavailable" ? {
  ...pile, selection_unavailable: true, selection_invalidated: false,
  expected_next_key: null, expected_next_members: [],
  selection_pending: detail.selection_pending ?? null,
} : typeof detail.selection_revision !== "string" || !Array.isArray(detail.expected_next_members) ? {
  // The post-model commit guard can detect staleness after streaming began, when it cannot safely
  // promise a replacement capture. Invalidate the old marker until the authoritative GET returns.
  ...pile, selection_unavailable: false, selection_invalidated: true,
  expected_next_key: null, expected_next_members: [],
  selection_pending: detail.selection_pending ?? null,
} : {
  ...pile, selection_unavailable: false, selection_invalidated: false,
  selection_revision: detail.selection_revision,
  expected_next_key: detail.expected_next_key ?? null,
  expected_next_members: [...detail.expected_next_members],
  selection_pending: detail.selection_pending ?? null,
}) : pile;

// Until durable Current lands, reload restores the latest explicitly surfaced card. Passive
// watcher cards stay readable in history but cannot silently become the conversation subject.
export const restorableCurrent = (messages) => [...(messages || [])].reverse().find((message) =>
  message?.card && !message.card.background_event
  && !["brief", "setup", "agentdone", "setup_questions", "words"].includes(message.card.kind))?.card || null;   // a set-up's questions, a line's own words: not an item
// Which line carries the action words. It is the LAST thing Taskuary said, card or no card: an answer
// to a typed question offers the same verbs as the line that introduced the item, and a receipt is not a
// place to act. interactiveCardIndex is about the card inside the bubble and stays separate.
export const lastSaidIndex = (messages) => {
  for (let index = (messages || []).length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message?.role !== "assistant") continue;
    // A passive notice is something that HAPPENED, not somewhere to act - it is not about the thing on
    // the table, and letting it take the words moved them off the item the owner was working on the
    // moment a background update landed. interactiveCardIndex skips these for the same reason.
    if (message.card?.background_event) continue;
    return index;
  }
  return -1;
};
// ...except a receipt that CARRIES its way on: "Not done", a cancel, a sweep put Try again or Next on it, and with the
// words held by the line above they were never drawn - a failed act ended on an empty row (2026-10-07)
// A LIVE ITEM CARD keeps them, though: its words are its own buttons (Reply, Make a task...), and a receipt under it saying
// "use the buttons on the card" took them away. A proposal is not such a card - a failed one is exactly the receipt's case.
export const lastActIndex = (messages) => {
  const said = lastSaidIndex(messages), m = messages?.[said];
  if (said >= 0 && said === interactiveCardIndex(messages) && !m.proposal && m.card?.kind !== "proposal") return said;
  for (let index = (messages || []).length - 1; index > said; index -= 1) {
    if (messages[index]?.role === "receipt" && chipsOf(messages[index]).length) return index;
  }
  return said;
};
// The words offered under one line: the item's own verbs, or a clarifying choice the assistant asked
// with (OPTIONS) - which goes back as words, not as a verb. Never both: one row, one place to look.
export const chipsOf = (message) => {
  const options = (message?.options || []).map((o) => ({ ask: o, label: o }));
  if (options.length) return options;
  return message?.chips || message?.card?.chips || [];
};
// ...and a RECEIPT's, with its task and its bug report among them: both were buttons drawn in the line, against "no button in line
// ever" (the owner, 2026-10-06) - an Open TQ-x and a Report this bug stood under a failure in the chat (2026-10-17)
// ...and a SEND'S receipt, which is where the item now stands (the owner, 2026-10-18: "sending and closing are two steps"): Mark
// done while there is a task to close - never on an item with none - and Next. The server's own (concierge.sent_chips) match these.
export const sentChips = (tid, ref = null) => ({ chips: [...(tid ? [{ verb: "close", tid, ref, label: label("close") }] : []), { verb: "next", label: label("next") }] });
export const receiptChips = (m) => {
  const own = chipsOf(m);
  return [...own,
    ...(m?.tid && !own.some((c) => c.verb === "open" || c.verb === "opentask") ? [{ verb: "opentask", tid: m.tid, label: `Open ${m.ref || "the task"}` }] : []),
    ...(m?.status === "error" ? [{ verb: "bug", text: m.text, label: label("report_bug") }] : [])];
};
// A card whose verb was pressed is put down at once (`done`), not when the next card arrives: the
// settle and the next pick take a second, and a card still standing there gets pressed twice (the
// owner, 2026-09-25, on "All read, next"). It stays the newest card, so nothing older comes back to life.
// The card folded on the table is the one whose key the canvas folded - and NOTHING folded is not a key. A proposal made with
// nothing on the table has no key, so `null === null` folded every one of them as it was drawn: "confirm below" over a title
// line with no Confirm under it, and a click on the line put some other task on the table (2026-10-06).
export const foldsAs = (folded, key) => folded != null && key != null && folded === key;
export const interactiveCardIndex = (messages) => {
  for (let index = (messages || []).length - 1; index >= 0; index -= 1) {
    if (messages[index]?.card && !messages[index].card.background_event) return messages[index].done ? -1 : index;
  }
  return -1;
};
// THE CARD DRAWN LIVE IS THE TABLE'S (the dead-end walk's RING, 2026-10-20): the canvas drew the newest item line while the rail ringed the
// table, so after a Next and a link to another task the rail ringed TQ-0005 over TQ-0001's live card - a chat read merged after the pull
// put the item's own durable line back above the one before it. The newest card still leads, unless it is another ITEM while the table's
// own line is in the chat and not put down; a proposal, the walk or the brief after it lead as before.
const keyed = (c, key) => c?.key === key || (c?.aliases || []).includes(key);
export const tableCardIndex = (messages, key) => {
  const at = interactiveCardIndex(messages), top = at >= 0 ? messages[at] : null;
  if (!key || !top || top.proposal || NOT_ITEMS.has(top.card.kind) || keyed(top.card, key)) return at;
  for (let i = (messages || []).length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m?.card && !m.card.background_event && !m.done && !m.proposal && keyed(m.card, key)) return i;
  }
  return at;
};
// ...and a RELOADED conversation knows only the server's word. The page's `done` mark does not travel in the history, so
// after "All read, next" on the last batch found nothing next, the reload drew the read batch live again while the server
// said nothing was on the table (the owner, 2026-10-02: "it reopens the same 4 again before disappearing"). Every item
// card that is not the server's Current comes back put down; a proposal, the set-up walk and the brief are not items.
const NOT_ITEMS = new Set(["proposal", "walk", "setup", "brief"]);
// A line's own WORDS ride the server's record as a `words` card ({kind: "words", chips}), but the live turn drew them as plain
// chips on a card-less line. Read back as a card, it was put down like an item and kept only Next: the end of the walk's
// "Open TQ-12" buttons were gone after a reload (the 2026-10-07 click-through). Read back, it is the line it was.
export const settledHistory = (messages, currentKey) => (messages || []).map((m) => {
  if (m?.card?.kind === "words") return { ...m, chips: m.chips || m.card.chips || [], card: null };
  const c = m?.card;
  if (!c || c.background_event || m.proposal || NOT_ITEMS.has(c.kind)) return m;
  return currentKey && (c.key === currentKey || (c.aliases || []).includes(currentKey)) ? m : { ...m, done: true };
});

// A live task changes keys as ownership changes: msg:<mid> before dispatch, agent:<tid> while an
// agent has it. The task id is the stable identity across that hand-off.
export const followsItem = (card, fresh) => !!(card && fresh && (fresh.key === card.key
  || (fresh.processing_id && fresh.aliases?.includes(card.key))
  || (fresh.tid && fresh.tid === card.tid && fresh.lane === "working")));
export const currentItemFromPile = (current, pile) => {
  if (!current) return null;
  const items = pile?.items || [];
  // A server response scoped to Current is authoritative even when it says null. The one existing
  // compatibility transition is a dispatched message becoming its task's working-agent row; that
  // same-tid row is the accepted stable identity until shared canonical selection replaces it.
  if (pile && Object.prototype.hasOwnProperty.call(pile, "current")) {
    if (followsItem(current, pile.current)) return pile.current;
    return current.tid ? items.find((i) => i.tid === current.tid && i.lane === "working") || null : null;
  }
  return items.find((i) => i.key === current.key)
    || (current.tid ? items.find((i) => i.tid === current.tid && i.lane === "working") : null)
    || null;
};

// A presentation revision covers the complete card and every backing input its lazy detail reads.
// When it changes, use the server's complete replacement. Spreading over the old card would retain
// fields that were deliberately removed, such as a cleared draft, preview, or agent tail.
export const currentPresentationChanged = (current, fresh) => {
  if (!current || !fresh) return current !== fresh;
  if (current.presentation_revision && fresh.presentation_revision)
    return current.presentation_revision !== fresh.presentation_revision;
  return JSON.stringify(current) !== JSON.stringify(fresh);
};
export const refreshCurrentPresentation = (current, fresh) =>
  currentPresentationChanged(current, fresh) ? fresh : current;

// The card under a line is decided by the item's KIND, never by the model. Every kind maps to
// exactly one card so a reload draws the same conversation.
// WHAT THIS ITEM IS ASKING OF YOU, and the words that say so - the assistant's answer to the task
// page's focusStage, and kept in the same precedence so the two cannot drift: a draft waiting for a
// yes, then an agent that stopped, then work nobody has started, then the job itself.
//
// The lane, not the kind, decides. `kind` alone sent a task handed to an agent that never started
// through `default: "message"` - drawn as "a person wrote something", with no list, no reason and
// no way to start it (the owner, 2026-09-14). A `working` lane is walked like every task (2026-10-21), and an item already in
// front of you can BECOME working while you read it: either way it is the agent's card.
export const assistantFocus = (item) => {
  if (!item) return { card: null, lead: "" };
  const who = item.agent || item.working || "the agent";
  if (item.lane === "working" && item.tid) return { card: "agent", lead: `${who} is working on this — nothing for you here yet.` };
  // ONE EVENT SEEN TWICE: an agent parked because it PROPOSED something is released by approving
  // that proposal, so the proposal is what you are shown - not a terminal at a prompt with the
  // thing that unblocks it out of reach. No rid means there is nothing proposed to show, and then
  // it is just a waving agent. taskLifecycle.focusStage carries the same exception, and the two
  // are asserted against each other so this file's "same precedence" promise is enforced.
  if (item.lane === "blocked" && subState(item) === "approval" && item.rid)
    return { card: "reply", lead: "An agent proposed this. Read it, then it runs only if you say so." };
  if (item.lane === "blocked") return { card: "agent", lead: `${item.why || says(subState(item), who)}.` };
  if (item.kind === "review" || item.kind === "action" || item.lane === "approve")
    return { card: "reply", lead: item.kind === "action"
      ? "An agent proposed this. Read it, then it runs only if you say so."
      : "A reply is drafted and waiting for your yes — read what they asked, then send it." };
  // "codex was handed it and has not started" - both halves wrong on the row that prompted it. A
  // session HAD run (08:10 to 10:56 on TQ-0515), so "has not started" was false, and naming the
  // worker made it read as a chosen specialist sitting idle rather than an app that went down under
  // it (the owner, 2026-09-14: "why does the lead say codex and not 'agent has it'?"). `queued` is a
  // statement about NOW: nothing is on it. Who, and what happened, is why_idle's to say - it knows. It was computed and
  // never shown, and the lead said "this one is on you" over a start that was only waiting for a free slot (2026-10-16).
  if (item.lane === "queued" && item.tid)
    return { card: "task", lead: item.why_idle || "No agent is on this right now." };
  return { card: cardKind(item), lead: item.why || "" };
};

const cardKind = (item) => {
  switch (item.kind) {
    case "review": case "action": return "reply";
    case "agent": return "agent";
    case "meeting": return "meeting";
    case "report": return item.dashboard ? "dashboard" : "report";     // a dashboard's row opens the dashboard (dashboards.py)
    case "agentdone": return "agentdone";
    case "idea": return "idea";
    case "triaging": return null;
    case "brief": return "brief";
    case "task": return "task";
    case "fyis": return "fyis";
    case "wrapup": return "wrapup";
    default: return "message";          // asked, todo, fyi - a person wrote something
  }
};

export const cardFor = (item) => (item ? assistantFocus(item).card : null);

// HOW LONG IT HAS WAITED ON YOU, beside the item's ref on the action row: the rail's gutter says it per row, but the eye is on the
// buttons when deciding, and an old ask looked the same there as a new one (the row-bot comparison, 2026-10-07). Only what is on
// you (lanes.onYou - a stopped agent and a failed check waited as long as an ask did), and only once it is an hour old - under
// that it is simply new, and saying so is noise.
export const waitedText = (item, now = Date.now()) => {
  if (!item || !onYou(item)) return "";
  const a = band(item.since || item.when, now);
  return !a || a.startsWith("<") || a.startsWith("in ") ? "" : `waiting ${a}`;
};

// the header's one line under "Taskuary" - its "on you" is the opener's and the greeting's (lanes.onYou). It counted only an
// agent's question and a reply waiting for a yes, so the lane worded "on you" was left out of the header's own "on you".
export const statusLine = (items, busy) => {
  if (busy) return "thinking…";
  const n = (items || []).length;
  if (!n) return "All caught up";
  const you = (items || []).filter((i) => onYou(i)).length;
  return `${n} in the pipe${you ? ` · ${you} on you` : ""}`;
};

// Unread is ranked by attention, not by the clock, so the dock names the LEVEL the rail is crossing (the owner, 2026-09-07: "the
// date on top makes no sense on the unread tab since we don't sort by date"). One level per thing triage decided: work is one
// run whoever is waiting on it, a landed result is not work, an idea nobody has judged is an fyi. FOR LATER is work walked past
// with Next or put away with Remind me (2026-09-23); ideas have a level of their own until made work or dismissed (2026-09-29).
// The levels, their words, hints, bands and order all live in lanes.json `sections` (lanes.js).
// ...and the rail's CLOCK and ids, which place it among its section (placeOrder): the card on the table - a press's answer, a row drawn
// ahead - can carry another arrival or none, and a pinned row put back by the card's clock went past rows of its own second while the
// server kept it above them (the release walk's sweep SWAP, 2026-10-25)
export const PLACEMENT = ["lane", "order_band", "surfaced", "surfaced_at", "put_down", "unread", "kind", "working", "state", "news",
  "arrived_at", "sort_at", "since", "when", "member_ids", "mid", "brief_today"];
export const placed = (row, card) => {
  const out = { ...row, ...card };
  for (const k of PLACEMENT) { if (k in row) out[k] = row[k]; else delete out[k]; }
  return out;
};
// A TASK PULLED ONTO THE TABLE from outside the pile - search, a name in the chat - has no row to lend it a place, and its card
// speaks through its newest message: a closed task under a GitHub notification was drawn in FYI (the owner, 2026-10-15). What
// you opened is on you while it is open; a message with no task keeps its own lane.
// ...but an AGENT on the table says what the agent is doing: the walk's shown mark takes a row it is showing out of the pile, and
// the agent that asked a question while it stood there read "on you" on the rail under a header saying it waited on you (G7)
const AGENT_LANES = ["blocked", "working", "stopped", "saved"];
// ...and so does any task whose agent is WORKING, whatever kind of card it came as: under Tasks, ring spinning, never on you
export const pulledRow = (card) => (card?.tid && ((card.kind === "agent" && AGENT_LANES.includes(card.lane)) || card.lane === "working")
  ? { ...card, put_down: false, deferred: false }
  : card?.tid ? { ...card, lane: "yours", order_band: 2, put_down: false, deferred: false } : { ...card });
// THE RAIL AS PRESSED: a press the server has not answered yet still moves its row (the put-down, ac051beb). `leaving`: the
// task being closed or deleted leaves the rail; `continuing`: a task whose session was just continued is drawn working - its
// ring spinning, where it is under Tasks - not two seconds later with the next pile (press audit B23b, 2026-10-01).
export const asPressed = (items, { leaving = null, continuing = null } = {}) => (!leaving && !continuing ? items
  : items.filter((i) => !leaving || i.tid !== leaving)
    .map((i) => (continuing && i.tid === continuing
      ? { ...i, lane: "working", order_band: 2, surfaced: false, put_down: false, deferred: false, working: i.working || i.agent || "agent" } : i)));
// ...and a put-down has LANDED when the server's pile no longer has the row - or has it put away: Remind me keeps the task on the
// rail under For later (`deferred`), so waiting for it to vanish hid a reminded task until a reload (UX walk, 2026-10-22)
export const putDownLanded = (items, tid) => { const r = (items || []).find((i) => i.tid === tid); return !r || !!r.deferred; };
// when a For later row comes back: its Remind me date (an open task walked past has no clock - it is back with the next walk)
export const backAt = (item) => item?.back_at || item?.defer_until || null;
// ...said by timeWords.bandUntil, and every other gutter age by timeWords.band - one rule for how a time reads
// a GOAL's gutter is its date, not its age: for a goal the date is the clock (spec 2026-10-12)
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const dueWord = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}` : "";
};
export const levelLabel = (level) => LEVEL_META[level]?.word || "";
// the levels actually present, in the order the rail draws them - the jump menu's entries
export const levelsOf = (items) => LEVEL_ORDER.filter((level) => (items || []).some((i) => levelOf(i) === level));

// The ink each level's heading takes. Importance exists on the CATEGORY and nowhere else in this
// product (the owner, 2026-09-16: "we don't have importance besides for the 4 categories"), so the
// heading is the only thing on the rail that carries a role colour - the dot beside a row is its
// SOURCE, and a row's own word is gone. theme.jsx ROLES, named rather than copied.
export const LEVEL_ROLE = { task: "you", later: "passed", reports: "info", ideas: "info", fyi: "muted" };

// ── how the rail divides the height it has ────────────────────────────────────────────────────
// tasks are NEVER capped: a task behind a "4 more" button is a task you do not do. Whatever is left over
// goes to reports, then fyi, each keeping a floor of two - below that a band is a heading and a
// button, which is worse than absent. If that still overflows nothing is crushed further and the
// rail scrolls, so the only thing ever below the fold is work, in rank order.
// The rail's own geometry, in one place - and it has to be what is actually PAINTED, or the rail
// overflows the screen it was measured against. Read off assistantView.css: a row is 30px + its 3px
// gap; a heading is 7 margin + 9/7 padding + its line + a 1px rule; a "more" button is 5 + 3/3 + its
// line + 2. FOOT is what sits under the last band - the pile's own padding and the scroller's.
export const ROW_PX = 33, HEAD_PX = 36, MORE_PX = 28, FOOT_PX = 64;
export const CAPPED = ["reports", "ideas", "fyi"];
export const FLOOR = 2;
// For later is sorted by when each comes back, soonest first (no time known sorts last); every other band keeps the server's order
const soonest = (a, b) => (Date.parse(String(backAt(a) || "").replace(" ", "T")) || Infinity) - (Date.parse(String(backAt(b) || "").replace(" ", "T")) || Infinity);
// the walk's clock for a row (funnel.order_key): when it ARRIVED - never its newest activity, or a reply or an agent moved it (the
// owner, 2026-10-22: "set by time, oldest to newest and then never move") - oldest first inside every section, reports too (2026-10-22:
// "reports should go oldest first like everything else")
const walkAt = (i) => Date.parse(String(i?.arrived_at || i?.sort_at || i?.since || i?.when || "").replace(" ", "T")) || 0;
// ...and a TIE IN THE SAME SECOND by ids that never change - the task number, then the row's first message, then the key - the server's
// own rule (funnel.place_id), line for line. A row put back by arrival alone went after every row of its second while the server had
// it before them: two dashboards filed together swapped and were drawn over each other as the rail moved (the dead-end walk's SWAP,
// 2026-10-25). Never insertion order, never a hash alone.
const num = (x) => (x === null || x === undefined || x === "" || x === true || x === false || !Number.isInteger(Number(x)) ? null : Number(x));
export const placeId = (i) => {
  const tid = num(i?.tid);
  const mids = (i?.member_ids || []).map(String).filter((m) => m.startsWith("message:")).map((m) => num(m.slice(8))).filter((n) => n !== null);
  const mid = tid !== null ? null : mids.length ? Math.min(...mids) : num(i?.mid);       // a task's own rows keep their key between them
  // ...and a row with neither (an idea, a review on its own) by its first member, kind then number - funnel.first_member
  const first = tid !== null || mid !== null ? "" : (i?.member_ids || []).map(String).map((m) => [m.slice(0, m.indexOf(":")), num(m.slice(m.indexOf(":") + 1))])
    .filter(([k, n]) => k && n !== null && n >= 0).map(([k, n]) => `${k}:${String(n).padStart(12, "0")}`).sort()[0] || "";
  return [tid === null ? 1 : 0, tid ?? 0, mid === null ? 1 : 0, mid ?? 0, first, String(i?.key || "")];
};
// a row's place inside its section (funnel.order_key past the section): today's brief, a known arrival, the arrival, then placeId
const placeOf = (i) => [i?.brief_today ? 0 : 1, walkAt(i) ? 0 : 1, walkAt(i), ...placeId(i)];
export const placeOrder = (a, b) => {
  const x = placeOf(a), y = placeOf(b);
  for (let k = 0; k < x.length; k += 1) if (x[k] !== y[k]) return x[k] < y[k] ? -1 : 1;
  return 0;
};
// ...and the age the rail's gutter says is that same clock, so the column reads in the order the rows are drawn
// (the last message was tried on 2026-10-22: placed by arrival, labelled by its newest mail, the column read 1d, 1d, 2h, 1d, 2h - a
// user reported the tasks out of order; the owner, 2026-10-23, chose the arrival)
export const arrivedAt = (i) => i?.arrived_at || i?.since || i?.when;
// ...and a reply never moves the row nor changes that age: it says "+N" beside it, the messages from others since the owner last opened
// it (the server's `new_n`), and the age's hover says both clocks (the owner, 2026-10-23). The row on the table has just been opened,
// so it wears none - the server's next pile has cleared it.
export const newMark = (i, isCur) => (!isCur && i?.new_n > 0 ? `+${i.new_n}` : "");
export const ageHover = (i) => [arrivedAt(i) && `arrived ${fmtDateTime(arrivedAt(i))}`, i?.last_at && `last message ${ago(i.last_at)}`]
  .filter(Boolean).join(" · ") || undefined;
// ...and the line under its title is the newest message, who said it and what
export const latestLine = (i) => (i?.latest?.text ? [i.latest.who, i.latest.text].filter(Boolean).join(": ") : "");
// A ROW FROM OUTSIDE THE PILE - the task on the table pulled by name, a batch's members put back - TAKES ITS PLACE in the rail's
// order: it was drawn first, above every row of its section, so the row on the table jumped to the top (2026-10-22: "on the table
// should never move them")
export const inOrder = (rows, extra) => (extra || []).reduce((out, x) => {
  const level = levelOf(x);
  const at = out.findIndex((r) => levelOf(r) === level && placeOrder(r, x) > 0);
  return at < 0 ? [...out, x] : [...out.slice(0, at), x, ...out.slice(at)];
}, [...(rows || [])]);
// `pin` {key, level}: the row on the table keeps the band it was in when it was opened (AssistantView's Pile). A task whose agent
// starts, asks or stops no longer changes band at all: every open task is under Tasks (the owner, 2026-10-21).
// ...and a pinned row sits in its band WHERE THE WALK'S ORDER PUTS IT: it kept its own lane's place in the server's order, so a row
// from a later band was drawn under every row of the band it was pinned to - a day-old task at the bottom of its band, below 1h
export const bandsOf = (items, pin = null) => {
  const held = (i) => !!pin?.level && i.key === pin.key;
  return LEVEL_ORDER
    .map((level) => {
      const rows = (items || []).filter((i) => (held(i) ? pin.level : levelOf(i)) === level);
      if (level === "later") return { level, items: [...rows].sort(soonest) };
      const moved = rows.find((i) => held(i) && levelOf(i) !== level);
      if (!moved) return { level, items: rows };
      const rest = rows.filter((i) => i !== moved);
      const at = rest.findIndex((i) => placeOrder(i, moved) > 0);
      return { level, items: at < 0 ? [...rest, moved] : [...rest.slice(0, at), moved, ...rest.slice(at)] };
    })
    .filter((b) => b.items.length);
};

// avail: pixels the rail can paint without scrolling. Returns {level: rows to draw} for the capped
// bands only; everything else draws in full. Pure, so test/funnelPile.test.mjs can pin the rule.
// ...and what to give back when the guess was still too generous. The cost model above is an
// estimate of what the browser will paint, and an estimate is always a little wrong - fonts, a
// wrapped heading, a scrollbar appearing and taking width. `trim` is the REAL overflow, measured
// after layout and converted to rows, taken off the noisiest band first (the owner, 2026-09-16:
// "why do i still see a scroll bar on the work tab").
export function trimCaps(caps, bands, rows) {
  const out = { ...caps };
  let left = Math.max(0, rows);
  for (const level of [...CAPPED].reverse()) {
    if (!left) break;
    const have = out[level];
    if (!Number.isInteger(have)) continue;
    const give = Math.min(left, Math.max(0, have - FLOOR));
    out[level] = have - give;
    left -= give;
  }
  return out;
}

export function fillCaps(avail, bands, { row = ROW_PX, head = HEAD_PX, more = MORE_PX } = {}) {
  const caps = {};
  const capped = (bands || []).filter((b) => CAPPED.includes(b.level));
  if (!capped.length) return caps;
  // the cost of a band drawn n deep - the "N more" button goes away once nothing is left hidden
  // ...and `total` is a band's whole count when part of it is not here as rows (the FYI tail, pileRows)
  const cost = (b, n) => n * row + (n < (b.total ?? b.items.length) ? more : 0);
  let used = bands.length * head
    + bands.filter((b) => !CAPPED.includes(b.level)).reduce((n, b) => n + b.items.length * row, 0);
  for (const b of capped) { caps[b.level] = Math.min(FLOOR, b.items.length); used += cost(b, caps[b.level]); }
  // ...then reports, then fyi, a row at a time while a row still fits
  for (const b of capped) {
    for (;;) {
      const n = caps[b.level];
      if (n >= b.items.length) break;
      const next = used - cost(b, n) + cost(b, n + 1);
      if (next > avail) break;
      used = next; caps[b.level] = n + 1;
    }
  }
  return caps;
}

// A live event says "something was written". If a FORCED pile load STARTED after the newest event
// of the burst arrived, that load read the database after the write committed (the event is sent
// on commit), so a second reload would fetch the same rows again. A press of Next did exactly that:
// the turn's own reload landed the fresh rows, and the settle's feed-changed still fired a fourth
// full build 1.5s later - the visible gap between the old rows vanishing and the next four appearing
// (2026-09-17). Compared against the load's START, never its end: a load that began before the
// write and finished after it read stale rows and must not be counted.
export const coveredByReload = (meta, forcedStartedAt) =>
  !!(meta && meta.lastAt && forcedStartedAt && meta.lastAt <= forcedStartedAt);

// A rail that came WITH an answer (a turn's, a settle's) was read on the server after that write;
// `generated_at` is when that read began, on the server's clock. Events older than it were seen by
// the read. It is never taken as later than now: a server clock ahead of ours must not cover a write
// the read did not see - the safe error is one reload too many, never one too few.
export const heldSince = (pile, now = Date.now()) => {
  const at = Number(pile?.generated_at);
  return Number.isFinite(at) && at > 0 ? Math.min(at, now) : now;
};

// ── walking one section (the canvas redesign, 2026-09-29) ──────────────────────────────────────
// Clicking a section's heading puts its first row on the table, and Next stays inside that section until it is empty -
// then it says so and the walk goes on as normal. The rows are the rail's own (bandsOf, so For later walks soonest
// first); the server's funnel.section_next is the same rule for the phone doorway.
export const sectionNext = (items, section, seen = new Set()) =>
  (bandsOf(items).find((b) => b.level === section)?.items || [])
    .find((i) => !i.settling && !seen.has(i.key) && !(i.aliases || []).some((a) => seen.has(a))) || null;
export const sectionDone = (section) => `${SECTION_WORDS[section] || section} done.`;

// ── the FYI tail (funnel.page_fyi) ─────────────────────────────────────────────────────────────
// Six months of plain FYI was most of a big mailbox's rail and of every answer, while the rail draws a handful of them. The
// page asks for FYI_PAGE of them whole; the rest come as `fyi_tail`, only the fields the page COUNTS by. So whatever DRAWS
// or ACTS reads pile.items - the row on the table and the walk's next pick are always among them - and whatever COUNTS
// (a heading, the day's opener, "in today", "N more fyi") reads pileRows, which is every row, the same as before paging.
export const FYI_PAGE = 50;
const tails = new WeakMap();
export const fyiTail = (pile) => {
  const t = pile?.fyi_tail;
  if (!t || !Array.isArray(t.rows) || !t.rows.length) return [];
  let rows = tails.get(t);
  if (!rows) {
    rows = t.rows.map((r) => {
      const o = { lane: t.lane, order_band: t.order_band };
      t.fields.forEach((f, n) => { if (f !== "shows_who") o[f] = r[n]; else if (r[n] != null) o.shows = { who: r[n] }; });
      return o;
    });
    tails.set(t, rows);
  }
  return rows;
};
export const pileRows = (pile) => {
  const tail = fyiTail(pile);
  return tail.length ? [...(pile?.items || []), ...tail] : (pile?.items || []);
};

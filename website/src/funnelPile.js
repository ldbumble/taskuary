import vocab from "../../taskuary/lanes.json" with { type: "json" };
import { says, subState } from "./laneSays.js";
export { says, subState };
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
// the 'report' lane (both just landed), but reading "report" on the coder's own summary is wrong (the
// owner, 2026-09-03: "it's not a report but agent awaiting little hand no?").
export const KIND_META = byKey(vocab.kinds);
export const rowMeta = (item) => ({ ...laneMeta(item?.lane), ...(KIND_META[item?.kind] || {}) });

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
export const nextMarkerKey = (pile, items, current) => {
  if (hasNextSelection(pile))
    return pile.expected_next_members[0] || pile.expected_next_key || null;
  const eligible = (item) => !item.settling && item.lane !== "working" && item.key !== current?.key;
  return ((items || []).find((item) => eligible(item) && !item.surfaced)
    || (items || []).find(eligible))?.key || null;
};
export const canAdvanceSelection = (pile, ready, only = null) => {
  if (!hasNextSelection(pile)) return (ready || []).length > 0;
  if (pile.selection_unavailable || pile.selection_invalidated) return false;
  if (pile.expected_next_key) return true;
  // An empty mail capture is still a guarded operation: the server returns exhausted:"mail", the
  // client drops that scope, and the following Next continues with non-mail work already in view.
  return only === "mail" && (ready || []).length > 0;
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
  && !["brief", "setup", "agentdone"].includes(message.card.kind))?.card || null;
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
// The words offered under one line: the item's own verbs, or a clarifying choice the assistant asked
// with (OPTIONS) - which goes back as words, not as a verb. Never both: one row, one place to look.
export const chipsOf = (message) => {
  const options = (message?.options || []).map((o) => ({ ask: o, label: o }));
  if (options.length) return options;
  return message?.chips || message?.card?.chips || [];
};
export const interactiveCardIndex = (messages) => {
  for (let index = (messages || []).length - 1; index >= 0; index -= 1) {
    if (messages[index]?.card && !messages[index].card.background_event) return index;
  }
  return -1;
};

// A live task changes keys as ownership changes: msg:<mid> before dispatch, agent:<tid> while a
// coder has it. The task id is the stable identity across that hand-off.
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
// no way to start it (the owner, 2026-09-14). A `working` lane never reaches the walk at all - the
// pile excludes it until the agent stops or asks - but an item already in front of you can BECOME
// working while you read it, and then it is the agent's card.
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
  // statement about NOW: nothing is on it. Who, and what happened, is why_idle's to say - it knows.
  if (item.lane === "queued" && item.tid)
    return { card: "task", lead: "This one is on you — no agent is on it right now." };
  return { card: cardKind(item), lead: item.why || "" };
};

const cardKind = (item) => {
  switch (item.kind) {
    case "review": case "action": return "reply";
    case "agent": return "agent";
    case "meeting": return "meeting";
    case "report": return "report";
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

// "in 12 min" / "now" / "2h ago" - how long an item has waited, or until a meeting starts
export const ageText = (iso, now = Date.now()) => {
  if (!iso) return "";
  const t = new Date(String(iso).replace(" ", "T")).getTime();
  if (Number.isNaN(t)) return "";
  const m = Math.round((t - now) / 60000);
  if (m > 0) return m < 60 ? `in ${m} min` : m < 1440 ? `in ${Math.floor(m / 60)}h` : `in ${Math.round(m / 1440)}d`;
  const a = -m;
  if (a < 2) return "now";
  if (a < 60) return `${a} min`;
  if (a < 1440) return `${Math.floor(a / 60)}h`;
  return `${Math.round(a / 1440)}d`;
};

// ...and the age as the WORK RAIL's gutter reads it. The rail is ranked, not dated, so the column's
// only job is "which of these has been sitting too long" - and an exact "22 min" invites arithmetic
// instead of an answer. Anything inside the first half hour is simply new, then hour by hour, then
// days (the owner, 2026-09-16: "within a half an hour say 30 min <, then per hour bands of time").
export const railAge = (iso, now = Date.now()) => {
  if (!iso) return "";
  const t = new Date(String(iso).replace(" ", "T")).getTime();
  if (Number.isNaN(t)) return "";
  const m = Math.round((t - now) / 60000);
  if (m > 0) return m < 60 ? `in ${m}m` : m < 1440 ? `in ${Math.floor(m / 60)}h` : `in ${Math.round(m / 1440)}d`;
  const a = -m;
  if (a < 30) return "< 30m";
  if (a < 60) return "< 1h";
  if (a < 1440) return `${Math.floor(a / 60)}h`;
  return `${Math.floor(a / 1440)}d`;
};

// ...and the same age as a SENTENCE. `ageText` answers "how far", which is why four cards appended
// " ago" to it and read "now ago" on anything under two minutes - and "in 3 min ago" on a stamp the
// server clocked a moment ahead of the browser (2026-09-10 audit).
export const agoText = (iso, now = Date.now()) => {
  const a = ageText(iso, now);
  return !a ? "" : a === "now" ? "just now" : a.startsWith("in ") ? a : `${a} ago`;
};

// the header's one line under "Taskuary"
export const statusLine = (items, busy) => {
  if (busy) return "thinking…";
  const n = (items || []).length;
  if (!n) return "All caught up";
  const you = (items || []).filter((i) => i.lane === "blocked" || i.lane === "approve").length;
  return `${n} in the pipe${you ? ` · ${you} on you` : ""}`;
};

// New cards and alerts carry the server's band. Old persisted cards use the same
// five-band fallback until their current presentation is refreshed.
const BAND = { blocked: 2, time: 1, approve: 2, broken: 2, asked: 2, yours: 2, queued: 2, stopped: 2, forgotten: 4, report: 3, fyi: 4, working: 5 };
export const attentionBand = (item) => {
  if (Number.isInteger(item?.order_band) && item.order_band >= 1 && item.order_band <= 5) return item.order_band;
  // a meeting that is not imminent, and any row whose lane this build does not know, are the
  // owner's to deal with - never a landed result, which is what band 3 now means
  if (item?.kind === "meeting" && (item.calendar_ready === false || item.mins > 15)) return 2;
  return BAND[item?.lane] ?? 2;
};
// Unread is ranked by attention, not by the clock, so a DATE over the rail said nothing about what
// you were looking at - "Saturday, Sep 5" sat over rows from three different days (the owner,
// 2026-09-07: "the date on top makes no sense on the unread tab since we don't sort by date"). The
// dock names the LEVEL the rail is currently crossing instead, and its menu jumps between them.
//
// One level per thing triage decided, and no level it did not: work is one run whoever is waiting
// on it, a landed result is not work, and an idea nobody has judged is an fyi. The words are the
// levels - processing_order.attention_band is the same list on the server.
export const LEVEL_META = {
  urgent: { word: "urgent", hint: "a meeting inside fifteen minutes, or a sender on your escalate list" },
  task: { word: "your task", hint: "an open task with no agent, a reply waiting for your yes, an agent waiting on your answer, a hand-off that has not started, a check that failed" },
  reports: { word: "reports", hint: "a report you set up landed, or an agent finished a job" },
  fyi: { word: "fyi", hint: "people told you things, and ideas nobody has turned into work - read them or don't" },
  agents: { word: "agents working", hint: "an agent has these; nothing for you until one stops or asks" },
};
export const LEVEL_ORDER = ["urgent", "task", "reports", "fyi", "agents"];
const LEVEL_OF_BAND = { 1: "urgent", 2: "task", 3: "reports", 4: "fyi", 5: "agents" };
export const levelOf = (item) => LEVEL_OF_BAND[attentionBand(item)] || "fyi";
export const levelLabel = (level) => LEVEL_META[level]?.word || "";
// the levels actually present, in the order the rail draws them - the jump menu's entries
export const levelsOf = (items) => LEVEL_ORDER.filter((level) => (items || []).some((i) => levelOf(i) === level));

// The ink each level's heading takes. Importance exists on the CATEGORY and nowhere else in this
// product (the owner, 2026-09-16: "we don't have importance besides for the 4 categories"), so the
// heading is the only thing on the rail that carries a role colour - the dot beside a row is its
// SOURCE, and a row's own word is gone. theme.jsx ROLES, named rather than copied.
export const LEVEL_ROLE = { urgent: "you", task: "you", reports: "info", fyi: "muted", agents: "working" };

// ── how the rail divides the height it has ────────────────────────────────────────────────────
// urgent, your task and agents working are NEVER capped: a task behind a "4 more" button is a task
// you do not do, and the agents band is bounded by how many agents you run. Whatever is left over
// goes to reports, then fyi, each keeping a floor of two - below that a band is a heading and a
// button, which is worse than absent. If that still overflows nothing is crushed further and the
// rail scrolls, so the only thing ever below the fold is work, in rank order.
// The rail's own geometry, in one place - and it has to be what is actually PAINTED, or the rail
// overflows the screen it was measured against. Read off assistantView.css: a row is 30px + its 3px
// gap; a heading is 7 margin + 9/7 padding + its line + a 1px rule; a "more" button is 5 + 3/3 + its
// line + 2. FOOT is what sits under the last band - the pile's own padding and the scroller's.
export const ROW_PX = 33, HEAD_PX = 36, MORE_PX = 28, FOOT_PX = 64;
export const CAPPED = ["reports", "fyi"];
export const FLOOR = 2;
export const bandsOf = (items) => LEVEL_ORDER
  .map((level) => ({ level, items: (items || []).filter((i) => levelOf(i) === level) }))
  .filter((b) => b.items.length);

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
  const cost = (b, n) => n * row + (n < b.items.length ? more : 0);
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

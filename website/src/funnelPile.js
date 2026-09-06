// The pipe, as the Assistant page draws it: what each lane is called and coloured, which item is a
// new arrival (it drops in from the top and slides to its slot), and which card goes under a line.
// Pure and dependency-free so it runs under bare node (test/funnelPile.test.mjs); colour is named
// by ROLE (theme.jsx ROLES) so this file cannot drift from the palette.

// Presentation lanes; the server supplies the five attention bands and item order.
export const LANES = ["blocked", "time", "approve", "broken", "asked", "forgotten", "report", "fyi", "working"];
export const LANE_META = {
  blocked:   { word: "agent waiting", role: "you",     mark: "👋", hint: "an agent stopped and is waiting on you — it is blocking work" },
  time:      { word: "coming up",     role: "working", mark: "⏱",  hint: "a meeting inside two hours, or an urgent sender" },
  approve:   { word: "reply pending", role: "you",     mark: "✉️", hint: "a reply or an action is drafted and waits for you" },
  broken:    { word: "a check failed", role: "bad",     mark: "🛠",  hint: "a report or workflow you set up could not run - the cause is in it" },
  asked:     { word: "asked you",     role: "working", mark: "🙋", hint: "a person asked you for something and nobody is on it" },
  forgotten: { word: "slipped",       role: "info",    mark: "🧵", hint: "the ask that slipped, the promise you made, the thread gone quiet" },
  report:    { word: "report",        role: "info",    mark: "📄", hint: "a report you set up landed, or an agent finished a job" },
  fyi:       { word: "fyi",           role: null,      mark: "👀", hint: "a person told you something — read it or don't" },
  working:   { word: "agent working", role: "working", mark: "⚙️", hint: "an agent has it — nothing for you until it stops or asks; it moves up when it needs your input" },
};
export const laneMeta = (lane) => LANE_META[lane] || LANE_META.fyi;

// A few KINDS carry more than their lane does. An agent's finished job and a report you set up share
// the 'report' lane (both just landed), but reading "report" on the coder's own summary is wrong (the
// owner, 2026-09-03: "it's not a report but agent awaiting little hand no?").
export const KIND_META = {
  agentdone: { word: "agent finished", role: "working", mark: "✅" },
  wrapup:    { word: "close it?",      role: "info",    mark: "🗂" },
};
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
export const cardFor = (item) => {
  if (!item) return null;
  // A message becomes the agent's live work without becoming a different historical message.
  // Lane is the current truth: once it is working, draw the agent controls instead of leaving the
  // old "nobody on it" message card and its Start button on screen.
  if (item.lane === "working" && item.tid) return "agent";
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
const BAND = { blocked: 2, time: 1, approve: 2, broken: 3, asked: 3, forgotten: 3, report: 3, fyi: 4, working: 5 };
const attentionBand = (item) => {
  if (Number.isInteger(item?.order_band) && item.order_band >= 1 && item.order_band <= 5) return item.order_band;
  if (item?.kind === "meeting" && (item.calendar_ready === false || item.mins > 15)) return 3;
  return BAND[item?.lane] ?? 3;
};
export const topAlert = (alerts, acked, current = null, shown = null) => {
  const band = current ? attentionBand(current) : 5;
  return (alerts || []).find((a) => !acked.has(a.key) && a.item !== current?.key && !shown?.has(a.item)
    && attentionBand(a) < band) || null;
};

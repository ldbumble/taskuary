// The pipe, as the Assistant page draws it: what each lane is called and coloured, which item is a
// new arrival (it drops in from the top and slides to its slot), and which card goes under a line.
// Pure and dependency-free so it runs under bare node (test/funnelPile.test.mjs); colour is named
// by ROLE (theme.jsx ROLES) so this file cannot drift from the palette.

// the lanes, most urgent first - the order the server ranks the pile in
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
  working:   { word: "agent working", role: "working", mark: "⚙️", hint: "an agent has it — nothing for you until it stops or asks; it drops to the front then" },
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

// A live task changes keys as ownership changes: msg:<mid> before dispatch, agent:<tid> while a
// coder has it. The task id is the stable identity across that hand-off.
export const followsItem = (card, fresh) => !!(card && fresh && (fresh.key === card.key
  || (fresh.tid && fresh.tid === card.tid && fresh.lane === "working")));
export const currentItemFromPile = (current, pile) => {
  if (!current) return null;
  const items = pile?.items || [];
  return (pile?.current?.key === current.key ? pile.current : null)
    || items.find((i) => i.key === current.key)
    || (current.tid ? items.find((i) => i.tid === current.tid && i.lane === "working") : null)
    || null;
};

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

// the pinned "by the way" bar: the first unacknowledged alert that OUTRANKS what is on the table -
// a meeting or an agent always does; a draft for your yes only while you are on something lesser
const BAND = { blocked: 0, time: 1, approve: 2, asked: 3, forgotten: 4, report: 5, fyi: 6, working: 9 };
export const topAlert = (alerts, acked, current = null, shown = null) => {
  const band = current ? (BAND[current.lane] ?? 3) : 5;
  // ...and never about something already drawn in the conversation: its own card is on screen, with
  // its own buttons, so a bar under it saying the same thing is noise (2026-09-03)
  return (alerts || []).find((a) => !acked.has(a.key) && a.item !== current?.key && !shown?.has(a.item)
    && (a.kind === "meeting" || a.kind === "agent" || (BAND[a.lane] ?? 3) < band)) || null;
};

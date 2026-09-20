// The Assistant report's block choice, as data. The panel is JSX; the decisions in it are here, so
// they can be tested under `node --test` without a DOM.
//
// BLOCKS mirrors taskuary/assistantblocks.py because SavedReportSummary renders in a list and must
// not fire a request per row. Two lists of the same thing drift, so
// test_assistant_blocks.py::test_the_page_and_the_server_name_the_same_blocks compares them - the
// settings schema learned this lesson already.
export const BLOCKS = [
  { id: "knowledge", label: "Knowledge base" },
  { id: "system_checks", label: "Configured systems" },
  { id: "threads", label: "What people said", days: 2 },
  { id: "ooo", label: "Out of office" },
  { id: "calendar", label: "Calendar", days: 2 },
  { id: "arrivals", label: "What arrived", days: 2 },
  { id: "done_this_week", label: "Done this week", days: 7 },
  { id: "open_work", label: "Open work" },
  { id: "already_said", label: "Already said" },
  { id: "notes", label: "My notes from last check" },
  { id: "waiting_on", label: "Waiting on them", hours: 24 },
  { id: "promised", label: "What I promised", hours: 24 },
  { id: "meeting_prep", label: "Meeting prep" },
  { id: "gone_quiet", label: "Work gone quiet", days: 3 },
  { id: "connectors", label: "Connectors mentioned", days: 30 },
  { id: "health", label: "App health" },
];

// One block's override, merged. Only the block touched is written: the rest of the choice is the
// owner's and a patch must not restate it.
export const blocksPatch = (blocks, id, patch) => ({ ...blocks, [id]: { ...(blocks?.[id] || {}), ...patch } });

// THE FIRST TICK MUST NOT UNTICK EVERYTHING ELSE. A saved `blocks` key is the whole truth (a block
// missing from it is off), so writing `{open_work: {on: true}}` onto a report that had no key would
// turn the other fifteen off. The first edit therefore writes the CURRENT state of every block,
// which is what the owner can see on the card, and edits that.
export const blockChoice = (cfg, rows) => cfg?.blocks && typeof cfg.blocks === "object" && !Array.isArray(cfg.blocks)
  ? cfg.blocks
  : Object.fromEntries((rows || []).map((r) => [r.id, { on: !!r.on, ...(r.window ? { [r.window.unit]: r.window.value } : {}) }]));

// A number the owner is still typing is not a number. An empty field stays empty rather than
// snapping to 0, which would blank the block's window on the first backspace.
export const windowPatch = (blocks, id, unit, raw) => {
  const s = String(raw ?? "").trim();
  if (s === "") return blocksPatch(blocks, id, { [unit]: "" });
  const n = Math.max(1, Math.floor(Number(s)));
  return Number.isFinite(n) ? blocksPatch(blocks, id, { [unit]: n }) : blocks;
};

// What a SAVED config reads, without asking the server. Mirrors assistantblocks.resolve: `blocks`
// absent means the declared defaults (and a report with sources of its own reads none of them);
// `blocks` present is the whole truth, so a block missing from it is off.
export const blockRowsOf = (cfg) => {
  const raw = cfg?.blocks;
  const over = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : null;
  const named = raw !== undefined && raw !== null;
  const isolated = !!(cfg?.watch_source_ids?.length || cfg?.watch_sources?.length);
  return BLOCKS.map((b) => {
    const o = over?.[b.id];
    const on = o && typeof o === "object" ? !!o.on : named ? false : !isolated;
    const unit = b.days !== undefined ? "days" : b.hours !== undefined ? "hours" : null;
    return { id: b.id, label: b.label, on,
      window: unit ? { unit, value: (o && typeof o === "object" && o[unit]) || b[unit] } : null };
  });
};

// ── the five cards: Taskuary as a SOURCE ──────────────────────────────────────────────────────
// Sixteen rows was a table; the owner (2026-09-20): "different cards as data sources, the cards
// should be Taskuary itself... combine them as much as possible". Mirrors assistantblocks.CARDS
// (tests/test_prompt_sources.py keeps it true): a card is a group of blocks with one switch and the
// group's numbers, saved on the report as `taskuary_sources`, named in a prompt as [taskuary.<id>].
export const TASKUARY_CARDS = [
  { id: "messages", label: "Messages", blocks: ["threads", "ooo", "arrivals", "waiting_on", "promised"],
    knobs: [{ name: "days", label: "days back", default: 2 }, { name: "hours", label: "hours of silence", default: 24 }],
    says: "what people said by thread, who is out of office, what arrived, and the asks and promises waiting on somebody" },
  { id: "calendar", label: "Calendar", blocks: ["calendar", "meeting_prep"],
    knobs: [{ name: "days", label: "days ahead", default: 2 }],
    says: "the next days on the calendar, and the meetings worth preparing for" },
  { id: "work", label: "Work", blocks: ["open_work", "done_this_week", "gone_quiet"],
    knobs: [{ name: "done_days", label: "days of done work", default: 7 }, { name: "quiet_days", label: "days before work is quiet", default: 3 }],
    says: "open tasks, what got done, and work that has gone quiet" },
  { id: "memory", label: "Memory", blocks: ["already_said", "notes", "knowledge"], knobs: [],
    says: "what it already said, its note from the last check, and the knowledge base" },
  { id: "systems", label: "Systems", blocks: ["health", "connectors"],
    knobs: [{ name: "days", label: "days of mentions", default: 30 }, { name: "floor", label: "threads before it is worth saying", default: 3 }],
    says: "the app's own health, and the systems people keep naming that nothing here reads" },
];
// ...which block's window a card's number stands for, for a report saved before cards existed
const KNOB_BLOCK = { messages: { days: "threads", hours: "waiting_on" }, calendar: { days: "calendar" },
  work: { done_days: "done_this_week", quiet_days: "gone_quiet" }, systems: { days: "connectors" } };

// The cards a saved config amounts to. `taskuary_sources` present (even empty) is the whole truth;
// absent, the block choice - or the defaults - is shown AS cards (assistantblocks.to_cards), and
// the first save writes them, so nothing an owner configured moves under them.
export const cardsOf = (cfg) => {
  if (Array.isArray(cfg?.taskuary_sources)) {
    const seen = new Set();
    return cfg.taskuary_sources.filter((x) => x && typeof x === "object" && TASKUARY_CARDS.some((c) => c.id === x.card) && !seen.has(x.card) && seen.add(x.card))
      .map((x) => ({ type: "taskuary", card: x.card, ...Object.fromEntries(knobsOf(x.card).filter((k) => x[k.name] !== undefined).map((k) => [k.name, x[k.name]])) }));
  }
  const rows = Object.fromEntries(blockRowsOf(cfg).map((r) => [r.id, r]));
  return TASKUARY_CARDS.filter((c) => c.blocks.some((b) => rows[b]?.on))
    .map((c) => ({ type: "taskuary", card: c.id,
      ...Object.fromEntries(c.knobs.map((k) => [k.name, rows[KNOB_BLOCK[c.id]?.[k.name]]?.window?.value ?? k.default])) }));
};
export const knobsOf = (id) => TASKUARY_CARDS.find((c) => c.id === id)?.knobs || [];
export const cardLabel = (id) => TASKUARY_CARDS.find((c) => c.id === id)?.label || id;
// a number the owner is still typing is not a number (see windowPatch)
export const cardPatch = (cards, id, name, raw) => {
  const s = String(raw ?? "").trim();
  const v = s === "" ? "" : Math.max(0, Math.floor(Number(s)));
  if (s !== "" && !Number.isFinite(v)) return cards;
  return cards.map((c) => (c.card === id ? { ...c, [name]: v } : c));
};

// A prompt names a source as [type.label] - reports.source_key, lower-cased and single-spaced -
// and a Taskuary card as [taskuary.<card>]. The page writes these; the server reads them.
export const slug = (s) => String(s || "").toLowerCase().split(/\s+/).filter(Boolean).join(" ");
export const sourceKey = (src, i) => `${src?.type || "rest"}.${slug((src?.label || "").trim() || `${src?.type || "rest"} #${i}`)}`;
export const tokenOf = (key) => `[${key}]`;
// every source a report's prompt can name: Taskuary cards first, then the report's own sources
export const promptSources = ({ cards = [], sources = [] }) => [
  ...cards.map((c) => ({ key: `taskuary.${c.card}`, label: `Taskuary · ${cardLabel(c.card)}` })),
  ...sources.map((s, i) => ({ key: sourceKey(s, i + 1), label: (s.label || "").trim() || `${s.type || "rest"} #${i + 1}` })),
];

// The one line under a saved report: what it reads, named. Never a fixed sentence - that is what
// this whole feature replaced.
export const readsLine = (rows) => {
  const on = (rows || []).filter((r) => r.on && r.id !== "system_checks");
  if (!on.length) return "";
  const unit = (w) => (w.unit === "hours" ? `${w.value}h` : `${w.value}d`);
  return "Taskuary — " + on.map((r) => r.label + (r.window ? ` (${unit(r.window)})` : "")).join(", ");
};
export const cardsLine = (cards) => (cards?.length ? "Taskuary — " + cards.map((c) => cardLabel(c.card)).join(", ") : "");

// "~12.5k" reads; "~12500" does not, and "~0.3k" is a lie about precision below a hundred.
export const kilo = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n || 0));

// The money line appears only when the brain's price is known. A cost we cannot compute is absent,
// never zero and never a guess.
export const costLine = (totalTokens, runsPerDay, cost) => {
  const per = runsPerDay >= 1 ? `${Math.round(runsPerDay)} runs a day`
    : runsPerDay > 0 ? `${(runsPerDay * 7).toFixed(0)} runs a week` : "when it is run";
  return `~${kilo(totalTokens)} tokens per run · ${per}` + (cost != null ? ` · ~$${cost.toFixed(2)} a run` : "");
};

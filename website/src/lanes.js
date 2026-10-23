// THE RAIL'S RULES, read from taskuary/lanes.json - the same file the server reads (taskuary/lanes.py). Which section a row is in,
// what counts as on you, what each kind of row is called: each was a hand-kept table in several files on both sides and they had
// drifted - the opener counted waiting-on-them as on you and the greeting did not, and the header's "on you" left out the lane
// worded "on you". Pure and dependency-free but for button names, so it runs under bare node.
import vocab from "../../taskuary/lanes.json" with { type: "json" };
import { label } from "./buttons.js";

export const LANE = Object.fromEntries(vocab.lanes.map((l) => [l.key, l]));
// EVERY STATE'S WORD, once - a lane's, a kind's that overrides it, or a closed row's (lanes.json `states`): the task list's chips, the
// agent card's phase and the reply's "ready to send" read it here, never a typed copy (the cleanup round, 2026-10-18)
export const WORD = Object.fromEntries([...vocab.lanes, ...vocab.kinds, ...vocab.states].map((r) => [r.key, r.word]));
export const SECTIONS = vocab.sections;
export const SECTION = Object.fromEntries(SECTIONS.map((s) => [s.key, s]));
export const LEVEL_ORDER = SECTIONS.map((s) => s.key);
// the heading, and the same word inside a sentence ("For later" / "for later")
export const SECTION_WORDS = Object.fromEntries(SECTIONS.map((s) => [s.key, s.word]));
const fill = (hint) => hint.replace(/\{button:(\w+)\}/g, (_, id) => label(id));
export const LEVEL_META = Object.fromEntries(SECTIONS.map((s) => [s.key, { word: s.word.toLowerCase(), hint: fill(s.hint) }]));
// URGENT IS A SHADE, NOT A SECTION (the owner, 2026-10-22): its band is drawn in Tasks, at its arrival place (lanes.json `urgent`)
export const URGENT = vocab.urgent;
const LEVEL_OF_BAND = { ...Object.fromEntries(SECTIONS.filter((s) => s.band).map((s) => [s.band, s.key])), [URGENT.band]: URGENT.section };
export const ALERT_MIN = URGENT.minutes;
export const laneSection = (lane) => LANE[lane]?.section || "task";   // a lane this build does not know is work, never buried

// a meeting is urgent only inside ALERT_MIN; before that it is on the day, not yet on you (funnel._not_yet)
export const notYet = (item) => item?.kind === "meeting"
  && ("calendar_ready" in item ? !item.calendar_ready : item.mins != null && item.mins > ALERT_MIN);
// processing_order.attention_band: the first flag that holds decides
// ...a task an agent is WORKING is a task, level 2 like the rest - it was a fifth level, "Agents working" (the owner, 2026-10-21)
const band = ({ urgent, wait, actionable, result }) => urgent ? 1 : wait || actionable ? 2 : result ? 3 : 4;
// The server stamps every row with its band; a row without one (an old persisted card) gets the server's own rule (lanes.band_of)
export const attentionBand = (item) => {
  // ...a stamp from before (band 5) is read again, never taken as fyi
  if (Number.isInteger(item?.order_band) && item.order_band >= 1 && item.order_band <= 4) return item.order_band;
  if (item?.kind === "meeting") return band({ urgent: !notYet(item), actionable: true });
  const l = LANE[item?.lane] || {}, sec = laneSection(item?.lane);
  // a task its agent finished rides the report lane but is On you; an unjudged row the retry gave up on is the owner's
  return band({ urgent: !!(l.urgent || (l.urgent_request && item?.urgent_request)), wait: !!l.waits,
    actionable: sec === "task" || item?.kind === "agentdone" || (item?.lane === "unjudged" && !!item?.held), result: sec === "reports" });
};
// urgent - a meeting inside ALERT_MIN, an ask triage called urgent, an escalated sender: shaded in its place, and walked in it like any other row
export const isUrgent = (item) => attentionBand(item) === URGENT.band;
export const levelOf = (item) => {
  const b = attentionBand(item);
  // A GOAL is one row and never gone, and it STAYS IN TASKS (the owner, 2026-10-22): Next walking past it, or no news, moved it to For
  // later (spec 2026-10-12) - the rail-order rule wins. Only Remind me puts it there, as for any task (lanes.py level_of)
  // For later is what you PUT there with a date - Remind me - never a card merely shown (2026-10-08), and no longer Next: Next
  // moves the walk on and the task stays in Tasks (the owner, 2026-10-21)
  if (b === 2 && item?.deferred) return "later";
  if (b === 4 && item?.kind === "idea") return "ideas";
  return LEVEL_OF_BAND[b] || "fyi";
};

// blocked on the owner's answer or yes - an agent asked, a reply waits
export const waitsOnYou = (item) => !!LANE[item?.lane]?.waits;
export const isOwnersMove = (item) => LANE[item?.lane]?.on_you !== false;
// ON YOU, the one count the opener's headline, the greeting and the header give: under Tasks, in a lane that is the
// owner's move - waiting on THEM, or an agent working, sits under Tasks as the owner's task, but it is on somebody else
export const onYou = (item, level = levelOf(item)) => !item?.settling && !!SECTION[level]?.on_you && isOwnersMove(item);
export const toRead = (item, level = levelOf(item)) => !item?.settling && !!SECTION[level]?.to_read;

// EVERY KIND OF ROW: how a sentence counts it, whether it came in as mail, whether it is an agent's own news
export const KIND = vocab.item_kinds;
export const isMail = (item) => !!KIND[item?.kind]?.mail;
export const isAgentKind = (kind) => !!KIND[kind]?.agent;
export const kindSays = (kind, n) => `${n} ${(KIND[kind] || KIND.other)[n === 1 ? "one" : "many"]}`;
// the Advisor's own kinds of line: what its card and Timeline row call it, and how a report's last run counts it
export const IDEA = vocab.idea_kinds;
export const ideaWord = (kind) => (IDEA[kind] || IDEA.idea).word;
export const ideaCounted = (kind) => (IDEA[kind] || IDEA.idea).counted;

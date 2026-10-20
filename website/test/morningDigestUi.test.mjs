import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the Assistant draws the meeting rail for today's digest", () => {
  const cards = read("assistantCards.jsx");
  const strip = read("TodayMeetingsStrip.jsx");
  assert.match(cards, /card\.brief_today && <TodayMeetingsStrip \/>/);
  // ...and the screen the day opens on draws the day too - as the opener's agenda column now, not the grey strip (mock-up A, 2026-10-08)
  const view = read("AssistantView.jsx");
  const welcome = view.slice(view.indexOf('className="tq-welcome"'), view.indexOf('className="tq-modes"'));
  assert.match(welcome, /<DayOpener /);
  assert.match(cards, /export function DayOpener[\s\S]*?useCalendarToday\(\)/);
  assert.match(strip, /TODAY’S MEETINGS/);
  assert.match(strip, /useCalendarToday\(\)/);                                     // shown at once from the last answer
  assert.match(read("calendarToday.js"), /api\.get\("\/api\/calendar\/today"\)/);
});

test("Settings has no empty Agents destination and profile links go straight to Docs", () => {
  const settings = read("SettingsView.jsx");
  assert.doesNotMatch(settings, /agents: \{ title: "Agents"/);
  assert.doesNotMatch(settings, /"memory", "agents", "audit"/);
  // ...and where a model is saved opens THAT card: "the claude connection - open" landed on the Profiles shelf (2026-10-19 UI walk)
  assert.match(settings, /const goFromPanel = \(where\) => openAppLink\(ownerHref\(where\)\);/);
});

// "A +" (the owner, 2026-10-08): what changed while you were away rides on top of the opening card, with the Morning digest folded
// under it - the digest used to wait in Reports and was stale by the time the walk reached it
test("the opening card carries what changed and the digest, folded, on its top", () => {
  const view = read("AssistantView.jsx"), cards = read("assistantCards.jsx");
  assert.match(view, /top=\{<SinceBlock onOpen=\{\(k\) => pull\(k, null\)\} onReading=\{setMailReading\} \/>\}/);
  assert.match(view, /See the full digest ▾/);
  assert.match(view, /api\.post\(`\/api\/reports\/\$\{dg\.source_id\}\/rerun`\)/, "Write a fresh one runs the digest now");
  assert.match(view, /<DigestText text=\{dg\.text\} sourceId=\{dg\.source_id\} \/>/);
  assert.match(cards, /export function DayOpener\(\{ groups = \[\], onSection, top = null, loading = false \}\)/);
});

// the owner, 2026-10-14: "put the digest right away on load and the numbers ... in loading mode - same for morning digest until it shows up"
test("the opening card loads in place: counts and the digest say they are coming, and the digest opens folded", () => {
  const view = read("AssistantView.jsx"), cards = read("assistantCards.jsx"), turns = read("assistantTurns.js");
  assert.match(view, /spin\("Reading what came in…"\)/);
  assert.match(view, /: "Writing today's digest…"\)\}/);
  assert.match(view, /dg\.waiting \? `Not written yet - \$\{plural\(dg\.waiting, "email"\)\}/, "queued by Finish, it says it waits on the mail");
  assert.doesNotMatch(view, /shownFor\.current !== dg\.at/, "the digest opens folded - See the full digest opens it");
  assert.match(view, /data\?\.said \|\| data\?\.drawn/, "an opener drawn mid catch-up is read at once");
  assert.match(cards, /loading \? "Counting…" : onYou \? `\$\{onYou\} on you` : "Nothing on you"/);
  assert.match(turns, /turn\.card\?\.kind === "brief"/, "the opener filled in its place is redrawn, not skipped by id");
});

test("what was learned is its own line on the opening card, never a card that loses its slot", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /\{d\?\.learned\?\.line && <div className="tq-since-digest" data-tq-learned="">/);
  assert.match(view, /settings=docs&doc=learned&view=changes/);
});

// the whole card from the first day (the owner, 2026-10-15: "say calendar missing if not available")
test("the calendar side says none connected, unreadable or no meetings, with the way to connect one", () => {
  const cards = read("assistantCards.jsx");
  assert.match(cards, /Array\.isArray\(today\.sources\) && !today\.sources\.length \? "none"/);
  assert.match(cards, /No calendar connected/);
  assert.match(cards, /openAppLink\(place\("mail"\)\.href\)/);
});

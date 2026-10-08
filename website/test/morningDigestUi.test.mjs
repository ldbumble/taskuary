import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("Timeline and Assistant share the meeting rail for today's digest", () => {
  const feed = read("FeedView.jsx");
  const cards = read("assistantCards.jsx");
  const strip = read("TodayMeetingsStrip.jsx");
  assert.match(feed, /import TodayMeetingsStrip/);
  assert.match(feed, /<TodayMeetingsStrip \/>/);
  assert.doesNotMatch(feed, /const TodayStrip/);
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
  assert.match(settings, /where === "agents"[\s\S]*window\.location\.hash = "profiles";[\s\S]*onNavigate\?\.\("Docs"\)/);
});

// "A +" (the owner, 2026-10-08): what changed while you were away rides on top of the opening card, with the Morning digest folded
// under it - the digest used to wait in Reports and was stale by the time the walk reached it
test("the opening card carries what changed and the digest, folded, on its top", () => {
  const view = read("AssistantView.jsx"), cards = read("assistantCards.jsx");
  assert.match(view, /top=\{<SinceBlock onOpen=\{\(k\) => pull\(k, null\)\} \/>\}/);
  assert.match(view, /See the full digest ▾/);
  assert.match(view, /api\.post\(`\/api\/reports\/\$\{dg\.source_id\}\/rerun`\)/, "Write a fresh one runs the digest now");
  assert.match(view, /<DigestText text=\{dg\.text\} sourceId=\{dg\.source_id\} \/>/);
  assert.match(cards, /export function DayOpener\(\{ groups = \[\], onSection, top = null \}\)/);
});

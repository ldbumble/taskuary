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
// the owner, 2026-10-30: "it should just show the 2 cards your day then the tasks count. Under it the morning digest first few rows of it,
// then with more button"
test("the opening card is the day and the tasks, the digest's first lines under them, More for the rest", () => {
  const view = read("AssistantView.jsx"), cards = read("assistantCards.jsx");
  assert.match(view, /top=\{<SinceBlock onOpen=\{\(k\) => pull\(k, null\)\} onReading=\{setMailReading\} \/>\}/);
  assert.match(cards, /\{read\.map\(row\)\}[\s\S]{0,200}\{top\}\s*<\/div>/, "the digest stands under the two cards");
  assert.match(view, /<DigestText text=\{open \? dg\.text : preview\} sourceId=\{dg\.source_id\} \/>/, "its first lines, the whole on More");
  assert.match(view, /\{open \? "Less ▴" : "More ▾"\}/);
  assert.match(view, /api\.post\(`\/api\/reports\/\$\{dg\.source_id\}\/rerun`\)/, "Write a fresh one runs the digest now");
  assert.doesNotMatch(view, /data-tq-since-card|data-tq-learned/, "no away cards and no memory line on the opener");
  assert.match(cards, /export function DayOpener\(\{ groups = \[\], onSection, top = null, loading = false \}\)/);
});

// the owner, 2026-10-14: "put the digest right away on load ... same for morning digest until it shows up"
test("the opening card loads in place: the digest says it is coming", () => {
  const view = read("AssistantView.jsx"), cards = read("assistantCards.jsx"), turns = read("assistantTurns.js");
  assert.match(view, /: "Writing today's digest…"\)\}/);
  assert.match(view, /dg\.waiting \? `Not written yet - \$\{plural\(dg\.waiting, "email"\)\}/, "queued by Finish, it says it waits on the mail");
  assert.match(view, /data\?\.said \|\| data\?\.drawn/, "an opener drawn mid catch-up is read at once");
  assert.match(cards, /loading \? "Counting…" : tasks \? "Tasks" : "Nothing on you"/);
  assert.match(turns, /turn\.card\?\.kind === "brief"/, "the opener filled in its place is redrawn, not skipped by id");
});

// the whole card from the first day (the owner, 2026-10-15: "say calendar missing if not available")
test("the calendar side says none connected, unreadable or no meetings, with the way to connect one", () => {
  const cards = read("assistantCards.jsx");
  assert.match(cards, /Array\.isArray\(today\.sources\) && !today\.sources\.length \? "none"/);
  assert.match(cards, /No calendar connected/);
  assert.match(cards, /openAppLink\(place\("mail"\)\.href\)/);
});

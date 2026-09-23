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
  // ...and the screen the day opens on draws it too: the walk's opener took the digest's job (2026-09-23)
  const view = read("AssistantView.jsx");
  const welcome = view.slice(view.indexOf('className="tq-welcome"'), view.indexOf('className="tq-modes"'));
  assert.match(welcome, /<TodayMeetingsStrip \/>/);
  assert.match(strip, /TODAY’S MEETINGS/);
  assert.match(strip, /api\.get\("\/api\/calendar\/today"\)/);
});

test("Settings has no empty Agents destination and profile links go straight to Docs", () => {
  const settings = read("SettingsView.jsx");
  assert.doesNotMatch(settings, /agents: \{ title: "Agents"/);
  assert.doesNotMatch(settings, /"memory", "agents", "audit"/);
  assert.match(settings, /where === "agents"[\s\S]*window\.location\.hash = "profiles";[\s\S]*onNavigate\?\.\("Docs"\)/);
});

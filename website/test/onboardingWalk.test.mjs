import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

// The chip used to open an AI-led walk-through, which could not run before an AI was connected -
// which is exactly when somebody presses it.
test("Set up Taskuary opens the scripted walk, not a request for an AI to interpret", () => {
  const view = read("AssistantView.jsx");
  const fn = view.slice(view.indexOf("const setup = "), view.indexOf("const setup = ") + 1400);
  assert.match(fn, /\/api\/setup\/walk/);
  assert.doesNotMatch(fn, /concierge\/setup/);
});

test("the walk is a card kind of its own and keeps the trail", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /kind === "walk"/);
  assert.match(view, /walk: <WalkCard/);
});

test("a stop shows what you can do there, each with its own way in", () => {
  const cards = read("assistantCards.jsx");
  const card = cards.slice(cards.indexOf("export function WalkCard"));
  assert.match(card, /You can/);
  assert.match(card, /can\.map/);
  assert.match(card, /Next/);
  assert.match(card, /Finish/);
  assert.doesNotMatch(card, /Skip/);          // with only a position stored, skip and next are one act
});

test("a tab stop shows the tab, and a missing image never leaves a torn box", () => {
  const cards = read("assistantCards.jsx");
  const card = cards.slice(cards.indexOf("export function WalkCard"));
  assert.match(card, /card\.image &&/);
  assert.match(card, /alt=\{`The \$\{card\.title\} tab`\}/);
  assert.match(card, /onError/);
});

test("the AI stop opens the real terminal rather than describing one", () => {
  const cards = read("assistantCards.jsx");
  const card = cards.slice(cards.indexOf("export function WalkCard"));
  assert.match(card, /CliPane/);
  assert.match(card, /useCliSetup/);
});

test("nothing in the walk asks a model anything", () => {
  const cards = read("assistantCards.jsx");
  const card = cards.slice(cards.indexOf("export function WalkCard"), cards.indexOf("export function WalkCard") + 4000);
  for (const banned of ["/api/concierge/say", "/api/concierge/ai", "provider"]) {
    assert.doesNotMatch(card, new RegExp(banned.replace(/\//g, "\\/")), banned);
  }
});

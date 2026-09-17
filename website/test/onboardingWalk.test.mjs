import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { walkAdvances } from "../src/walkStep.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
// bounded, not open-ended: WalkCard is the file's last export today, but an open slice would drag
// in whatever gets appended after it later (a later card containing "Skip" would fail test 3).
const walkCard = (cards) => cards.slice(cards.indexOf("export function WalkCard"), cards.indexOf("export function WalkCard") + 4000);

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
  const card = walkCard(read("assistantCards.jsx"));
  assert.match(card, /You can/);
  // guarded against a skewed release where the server sends a stop with no `can` (PW-... /
  // ab82e00a: a UI bundle once shipped ahead of the server half it depended on)
  assert.match(card, /can \|\| \[\]\)\.map/);
  assert.match(card, /Next/);
  assert.match(card, /Finish/);
  assert.doesNotMatch(card, /Skip/);          // with only a position stored, skip and next are one act
});

test("a tab stop shows the tab, and a missing image never leaves a torn box", () => {
  const card = walkCard(read("assistantCards.jsx"));
  assert.match(card, /card\.image &&/);
  assert.match(card, /alt=\{`The \$\{card\.title\} tab`\}/);
  assert.match(card, /onError/);
});

test("the AI stop opens the real terminal rather than describing one", () => {
  const card = walkCard(read("assistantCards.jsx"));
  assert.match(card, /CliPane/);
  assert.match(card, /useCliSetup/);
});

test("nothing in the walk asks a model anything", () => {
  const card = walkCard(read("assistantCards.jsx"));
  for (const banned of ["/api/concierge/say", "/api/concierge/ai", "provider"]) {
    assert.doesNotMatch(card, new RegExp(banned.replace(/\//g, "\\/")), banned);
  }
});

// The one real decision in this file: does a move land on a stop, or end the walk. `walk.go`
// clamps anything outside the list to 0 and returns THAT, so branching on the response instead of
// the request would make Finish silently reopen stop 1 - this executes the predicate rather than
// grepping for a string that happened to look right.
test("walkAdvances lands on every real stop and ends on Finish or past the end", () => {
  const total = 14;
  assert.equal(walkAdvances(0, total), true);     // first stop
  assert.equal(walkAdvances(7, total), true);     // a middle stop
  assert.equal(walkAdvances(total - 1, total), true);  // last stop
  assert.equal(walkAdvances(total, total), false);     // one past the end
  assert.equal(walkAdvances(-1, total), false);        // Finish
});

// The nine keys used to be restated here, in capture-walk.mjs and in walk.py, with nothing tying
// them together - a tenth stop added to walk.py would ship silently with no image. This derives
// the truth from walk.py instead of repeating it, and checks capture-walk.mjs agrees.
test("every image walk.py asks for is one the capture script shoots", () => {
  const walkPy = readFileSync(fileURLToPath(new URL("../../taskuary/walk.py", import.meta.url)), "utf8");
  const wanted = [...walkPy.matchAll(/'\/walk\/(\w+)\.png'/g)].map((m) => m[1]);
  assert.equal(wanted.length, 9);
  const script = readFileSync(fileURLToPath(new URL("../capture-walk.mjs", import.meta.url)), "utf8");
  const shot = [...script.matchAll(/\["(\w+)",\s*"/g)].map((m) => m[1]);
  assert.deepEqual(new Set(wanted), new Set(shot), "walk.py and capture-walk.mjs disagree about which tabs have pictures");
  // walk.py names these; a stop whose image 404s degrades to a stop with no image, which is
  // survivable - but it should not happen because nobody ran the capture, or ran a truncated one.
  // existsSync alone passes on a 0-byte file, so also floor the size well under the real ~180-400KB.
  const dir = fileURLToPath(new URL("../public/walk/", import.meta.url));
  for (const key of wanted) {
    const f = `${dir}${key}.png`;
    assert.ok(existsSync(f), `missing walk image: ${key}.png`);
    assert.ok(statSync(f).size > 20000, `suspiciously small walk image: ${key}.png`);
  }
});

test("one viewport shoots all nine, or they read as nine different apps", () => {
  const src = readFileSync(fileURLToPath(new URL("../capture-walk.mjs", import.meta.url)), "utf8");
  assert.match(src, /setViewport/);
  assert.equal(src.match(/setViewport/g).length, 1);
});

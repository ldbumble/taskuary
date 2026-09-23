import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { walkAdvances } from "../src/walkStep.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
// bounded, not open-ended: WalkCard is the file's last export today, but an open slice would drag
// in whatever gets appended after it later (a later card containing "Skip" would fail test 3).
// the whole component, to its closing brace - a fixed 4,000 characters cut it off once its comments grew
const walkCard = (cards) => {
  const at = cards.indexOf("export function WalkCard");
  const end = cards.indexOf("\n}\n", at);
  return cards.slice(at, end < 0 ? undefined : end + 2);
};

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

test("a stop shows what you can do there, each with its own way in - three at most", () => {
  const card = walkCard(read("assistantCards.jsx"));
  assert.match(card, /You can/);
  // guarded against a skewed release where the server sends a stop with no `can` (PW-... /
  // ab82e00a: a UI bundle once shipped ahead of the server half it depended on)
  assert.match(card, /can \|\| \[\]\)\.slice\(0, 3\)/);   // five bullets a stop stopped being read by stop three
  assert.match(card, /Next/);
  assert.match(card, /Finish/);
  assert.doesNotMatch(card, /Skip/);          // with only a position stored, skip and next are one act
});

// "we also need a button to start over the walk through" (the owner, 2026-09-18). The server always
// had the reset; the card never offered it. Back is the same move as Next, the other way.
test("the walk can go back a stop and start over from the first", () => {
  const card = walkCard(read("assistantCards.jsx"));
  assert.match(card, /Start over/);
  assert.match(card, /onRestart/);
  assert.match(card, /Back/);
  assert.match(card, /onBack/);
  const view = read("AssistantView.jsx");
  assert.match(view, /\/api\/setup\/walk\/reset/);
  assert.match(view, /onBack=\{\(\) => actions\.walk\(m\.card\.n - 1\)\}/);
  assert.match(view, /onRestart=\{actions\.walkRestart\}/);
});

// The picture was squeezed to the card and cropped to a 130px strip of its corner: a search box and
// half a heading (the owner, 2026-09-18: "the images look unclear"). Whole, and it is the way in.
test("a tab stop shows the whole tab, clickable, and a missing image never leaves a torn box", () => {
  const card = walkCard(read("assistantCards.jsx"));
  assert.match(card, /card\.image &&/);
  assert.match(card, /alt=\{`The \$\{card\.title\} tab`\}/);
  assert.match(card, /onError/);
  assert.match(card, /className="tq-walk-shot"/);
  assert.doesNotMatch(card, /maxHeight: 130/);
  assert.match(card, /onClick=\{\(\) => go\(card\.goto\)\}/);
  const css = read("assistantView.css");
  assert.match(css, /\.tq-walk-shot \{[^}]*aspect-ratio: 1280 \/ 760/);   // the capture's own shape, so nothing is cropped
});

// A window onto the tab, not a picture of it (the owner, 2026-09-23: "maybe skip the images and just have a
// window into settings you can scroll. like we have session window"). The Assistant stop keeps its picture:
// the walk runs inside the Assistant. Tasks' own first pick stays in the window instead of leaving the walk.
test("a tab stop is the tab itself in a scrollable window, and the Assistant stop keeps its picture", () => {
  const cards = read("assistantCards.jsx");
  const table = cards.slice(cards.indexOf("const TAB_WINDOWS"), cards.indexOf("function TabWindow"));
  for (const stop of ["connections", "docs", "settings", "board", "tasks", "reports", "hub"]) assert.match(table, new RegExp(`${stop}: React\.lazy`));
  assert.doesNotMatch(table, /assistant:/);
  assert.match(cards, /onSelect=\{setSel\} selected=\{sel\}/);
  assert.match(cards, /card\.image && !TAB_WINDOWS\[card\.key\]/);
  assert.match(read("assistantView.css"), /\.tq-walk-window \{[^}]*overflow: auto/);
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
  // Review retired as a tab and its stop folded into Tasks (2026-09-22): the count follows
  // walk.py, and the pairing below is what this test is actually for.
  assert.ok(wanted.length >= 8, `walk.py asks for ${wanted.length} pictures`);
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

// A FILE ON DISK IS NOT THE SAME CLAIM AS THE APP SERVING IT. The nine pictures were in the repo,
// in the vite output and in the wheel, and every one 404ed because only /assets was mounted. The
// route is proven over HTTP in tests/test_onboarding_walk.py; this keeps the mount from being read
// as dead code by somebody looking at server.py alone.
test("the pictures have a route of their own, because /assets is only the hashed build output", () => {
  const server = readFileSync(fileURLToPath(new URL("../../taskuary/server.py", import.meta.url)), "utf8");
  assert.match(server, /app\.mount\('\/walk', StaticFiles/);
});

// Six stops walked past drew six near-identical rows, each with the message avatar AND the card's
// own mark, and nothing but the title - it read as six things the assistant had said.
test("a stop you have walked past is a numbered step, not a message", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /const passed = !live && kind === "walk"/);
  assert.match(view, /\{!passed && <div className="avatar">/, "no second mark beside the card's own");
  assert.match(view, /tq-step-done/);
  assert.match(view, /of \{m\.card\.total\}/, "it says which step of how many");
  assert.match(read("assistantView.css"), /\.tq-step-done/);
});

// The header chip is tq-phone-hide, and it was the only door to the whole of this guidance.
test("the walk is reachable on a phone", () => {
  const view = read("AssistantView.jsx");
  const welcome = view.slice(view.indexOf('className="tq-welcome"'), view.indexOf('className="tq-welcome"') + 2400);
  const entry = welcome.slice(welcome.lastIndexOf("<button", welcome.indexOf("Set up Taskuary")), welcome.indexOf("Set up Taskuary"));
  assert.ok(entry.includes("onClick={setup}"), "the welcome block opens the same scripted walk");
  assert.doesNotMatch(entry, /tq-phone-hide/, "and it is not hidden on the device that needs it");
});

// The scripted walk took the identifier `setup`, and with it the welcome block's button - so the
// chip reading "Set up a report or workflow" opened the fourteen-stop tour of the app instead.
test("setting something up and walking the app are two different doors", () => {
  const view = read("AssistantView.jsx");
  const at = view.lastIndexOf("Set up a report or workflow");     // the button, not the comment above askSetup
  const chip = view.slice(view.lastIndexOf("<button", at), at);
  assert.ok(chip.includes("onClick={askSetup}"), "it asks what to set up");
  assert.match(view, /const askSetup = \(\) =>/);
  assert.match(view, /kind: "setup"/, "and the card it pushes still exists");
});

// Rows 2 and 4 both read "Connections" and went to the AI CLI agents page and the connector list.
test("a row's button names what it opens, in words the server owns", () => {
  assert.match(read("SetupWizard.jsx"), /s\.goto\?\.label \|\| s\.goto\?\.tab/);
  assert.match(walkCard(read("assistantCards.jsx")), /card\.goto\.label \|\| `Open \$\{card\.goto\.tab\}`/);
  const setupPy = readFileSync(fileURLToPath(new URL("../../taskuary/setup.py", import.meta.url)), "utf8");
  const labels = [...setupPy.matchAll(/'label': '([^']+)'/g)].map((m) => m[1]);
  assert.equal(labels.length, 5);
  assert.equal(new Set(labels).size, 5, `two rows wear the same button: ${labels}`);
});

// A box only where there is something to complete: the first five stops carry the checklist's own
// `done`, the other nine are a tour of the app, and an empty box beside "the Timeline" would invent
// a chore nobody has (the owner, 2026-09-17: "show check boxes if it's done. Make the walk through
// accurate to what was completed").
test("a stop that can be completed wears a box, and says which way it is ticked", () => {
  const cards = read("assistantCards.jsx");
  const walk = cards.slice(cards.indexOf("export function WalkCard"), cards.indexOf("export function", cards.indexOf("export function WalkCard") + 10));
  assert.match(walk, /"done" in card &&/);          // presence, not truthiness: false must still show a box
  assert.match(walk, /card\.done \? "\u2611" : "\u2610"/);
  assert.match(walk, /title=\{card\.done \? "already done" : "not done yet"\}/);
});

// The done-green line says what it IS. A bare noun there - "Outlook mail, Microsoft Teams, Telegram"
// directly above "You can connect a mailbox" - read as a heading for the instructions under it.
test("what is already set up says so, for every stop and not just one", () => {
  const cards = read("assistantCards.jsx");
  assert.doesNotMatch(cards, /card\.key === "ai" \? `Already set up/);
});

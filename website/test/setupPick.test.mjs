// THE ADVISOR LIGHTS THE REAL CONTROL ON SETUP (the owner, 2026-10-19: "update the advisor and make it work on setup. Make sure it's
// correct"). A browser walk found the line naming a move while nothing on the screen was lit, naming a card by a word the shelf did not
// show, and - on a fresh home - lighting ChatGPT (the shelf's first) beside a Claude card that read "Connected - pick it to make it your
// AI". The move is the card itself, or the open card's own button, or the row's Next - never a button of the Advisor's own.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { buttonOf, cardOf } from "../src/setupSteps.js";

const read = (f) => fs.readFileSync(path.join(process.cwd(), "src", f), "utf8");
const st = (aiDone, mailDone = false) => ({ rail: [{ key: "ai", done: aiDone, open: true }, { key: "mail", done: mailDone, open: aiDone }] });
const go = () => {};
const shelf = [{ key: "c1", title: "ChatGPT", state: "off", go }, { key: "c2", title: "Anthropic API", state: "off", go },
  { key: "cli-claude", title: "Claude", state: "on", go }, { key: "cli-codex", title: "Codex", state: "off", go }];

test("a fresh home lights the AI already connected here, not the shelf's first card", () => {
  assert.equal(cardOf(st(false), "ai", shelf).title, "Claude");
  const two = shelf.map((c) => (c.key === "cli-codex" ? { ...c, state: "on" } : c));
  assert.equal(cardOf(st(false), "ai", two).title, "Claude", "several connected: the first the shelf shows");
  assert.equal(cardOf(st(false), "ai", shelf.map((c) => ({ ...c, state: "off" }))).title, "ChatGPT", "none connected: the shelf's first");
});

test("a failing card leads - its fix is on it - and a card that cannot be pressed is never the move", () => {
  const mail = [{ key: "c7", title: "Outlook mail", state: "off", go }, { key: "c8", title: "Gmail", state: "failing", go }];
  assert.equal(cardOf(st(true), "mail", mail).title, "Gmail");
  assert.equal(cardOf(st(false), "ai", [{ key: "c1", title: "ChatGPT", state: "on" }, ...shelf.slice(1)]).title, "Claude");
});

test("no card once the step is done, while a card is open or a pick is under way, or on a step that is not a shelf", () => {
  assert.equal(cardOf(st(true), "ai", shelf), null);
  assert.equal(cardOf(st(true, true), "mail", shelf), null);
  assert.equal(cardOf(st(false), "ai", shelf, true), null);
  assert.equal(cardOf(st(true), "about", shelf), null);
});

test("the open setup's button to light is its filled one, else its outlined one - never a plain text button", () => {
  const b = (label, filled = false, outlined = false) => ({ label, filled, outlined });
  assert.equal(buttonOf([b("Report this bug"), b("Try again", false, true), b("Update Codex", true)]).label, "Update Codex");
  assert.equal(buttonOf([b("Cancel"), b("Open the sign-in page", false, true)]).label, "Open the sign-in page");
  assert.equal(buttonOf([b("Check now"), b("Show details")]), null);
});

test("the Advisor adds no button of its own: the card, the open setup's button or the row's verb is lit where it stands", () => {
  const src = read("FirstRun.jsx");
  assert.doesNotMatch(src, /setup:pick|pickRow|pickOf/, "no 'Connect <card>' on the row");
  assert.match(src, /const toneOf = \(id\) => \(id === rowLit \? "p" : "s"\)/, "one filled verb, and only when the move is on the row");
  assert.match(src, /<Light root=\{rootRef\} card=\{litCard\?\.key \|\| ""\} canvas=\{canvas\} onShown=\{onShown\} \/>/);
  assert.match(src, /detail=\{<Box data-tq-setup-scope="">\{open \? detail : cliDetail\}<\/Box>\}/);
  assert.match(src, /<Box data-tq-setup-scope=""><SetupDone/);
  assert.match(src, /THE ADVISOR LIGHTS THE REAL CONTROL \(the owner, 2026-10-19/, "the ruling is written where the old one stood");
  assert.match(read("ConnectorsView.jsx"), /data-tq-card=\{c\.key\}/);
  assert.match(read("assistantView.css"), /\[data-tq-card\]\[data-tq-setup-lit\]/);
});

test("the line names the lit control by the words the screen draws on it", () => {
  const src = read("FirstRun.jsx");
  assert.doesNotMatch(src, /Microsoft 365 is one sign-in/);
  assert.match(src, /const named = canvas \? shown\.label : litCard \? litCard\.title : /, "a card by its title, a button by its own label");
  assert.match(src, /else if \(!said && named && !lineRef\.current\.includes\(named\)\)/, "a line that does not name it ends by naming it");
  assert.match(src, /onShown\(el && canvas \? \{ label: \(el\.innerText \|\| ""\)\.trim\(\)/, "the button's label is read off the button");
});

test("About your work lights its own move - Next, or Write it while there is no description - and the dock lights about:next", () => {
  const about = read("FirstRunAbout.jsx");
  assert.match(about, /id: "about:next", group: "decide", tone: writeLit \? "s" : "p"/);
  assert.match(about, /data-tq-setup-lit=\{writeLit \? "about" : undefined\}/);
  assert.match(about, /Then press \$\{nextLabel\}\./);
  assert.match(read("AssistantView.jsx"), /\/\^\(setup\|about\):\/\.test\(String\(x\.id\)\) && x\.tone === "p" && !x\.disabled/);
});

test("the dock fills the setup verb it is told and nothing else", async () => {
  const { rowOf } = await import("../src/actionRow.js");
  const v = (id, extra = {}) => ({ id, group: "decide", tone: "s", label: id, ...extra });
  const list = [v("setup:back", { group: "next" }), v("setup:next", { tone: "p", label: "Next" })];
  assert.deepEqual([...rowOf({ ref: "", list }, { id: "setup:next" }).decide].filter((x) => x.tone === "p").map((x) => x.id), ["setup:next"]);
  assert.deepEqual([...rowOf({ ref: "", list }).decide].filter((x) => x.tone === "p"), [], "nothing named: nothing lit");
});

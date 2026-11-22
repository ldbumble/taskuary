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

test("the AI already connected here is lit; with none connected no AI card is - the person picks, Taskuary never does", () => {
  assert.equal(cardOf(st(false), "ai", shelf).title, "Claude");
  const two = shelf.map((c) => (c.key === "cli-codex" ? { ...c, state: "on" } : c));
  assert.equal(cardOf(st(false), "ai", two).title, "Claude", "several connected: the first the shelf shows");
  // the owner, 2026-10-20: "the advisor says claude is installed, set it up?? ... stop assuming that ... let them choose the AIs"
  assert.equal(cardOf(st(false), "ai", shelf.map((c) => ({ ...c, state: "off" }))), null, "none connected: no vendor is lit");
  const mail = [{ key: "c7", title: "Outlook mail", state: "off", go }, { key: "c8", title: "Gmail", state: "off", go }];
  assert.equal(cardOf(st(true), "mail", mail).title, "Outlook mail", "the email step still lights the shelf's first");
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


test("the dock fills the setup verb it is told and nothing else", async () => {
  const { rowOf } = await import("../src/actionRow.js");
  const v = (id, extra = {}) => ({ id, group: "decide", tone: "s", label: id, ...extra });
  // ...in the Nav pill now: Back and Next in their own slots (the owner, 2026-11-03), and a fix (Install) on the row beside it
  const list = [v("setup:back", { group: "back" }), v("setup:next", { group: "next", tone: "p", label: "Next" }), v("setup:install", { tone: "p" })];
  const named = rowOf({ ref: "", list }, { id: "setup:next" });
  assert.equal(named.next.tone, "p"); assert.equal(named.back.tone, "s"); assert.deepEqual(named.decide.filter((x) => x.tone === "p"), []);
  assert.deepEqual(rowOf({ ref: "", list }, { id: "setup:install" }).decide.filter((x) => x.tone === "p").map((x) => x.id), ["setup:install"]);
  assert.equal(rowOf({ ref: "", list }, { id: "setup:install" }).next.tone, "s");
  const none = rowOf({ ref: "", list });
  assert.deepEqual([...none.decide, none.next].filter((x) => x.tone === "p"), [], "nothing named: nothing lit");
});

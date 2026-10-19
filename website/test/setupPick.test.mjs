// THE STEP'S PICK IS A LIT MOVE (2026-10-19): on Your email the line said "Microsoft 365 is one sign-in" over a card reading "Outlook
// mail", Back was plain and Next was off - nothing on the row to press. The shelf's first card is offered on the row, by its own title.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { pickOf } from "../src/setupSteps.js";

const st = (mailDone) => ({ rail: [{ key: "ai", done: true, open: true }, { key: "mail", done: mailDone, open: true }] });
const cards = [{ title: "Outlook mail", go: () => "opened" }, { title: "Gmail", go: () => {} }];

test("an undone step offers its shelf's first card, by its title, and pressing it is the card's own press", () => {
  const p = pickOf(st(false), "mail", cards);
  assert.equal(p.title, "Outlook mail");
  assert.equal(p.run(), "opened");
});

test("no pick once the step is done, while a pick is under way, or on a step that is not a shelf", () => {
  assert.equal(pickOf(st(true), "mail", cards), null);
  assert.equal(pickOf(st(false), "mail", cards, true), null);
  assert.equal(pickOf(st(false), "about", cards), null);
  assert.equal(pickOf(st(false), "mail", [{ title: "Outlook mail" }]), null, "a card that cannot be pressed is not offered");
});

test("the row draws the pick lit and the line names the card the shelf shows", () => {
  const src = fs.readFileSync(path.join(process.cwd(), "src", "FirstRun.jsx"), "utf8");
  assert.match(src, /id: "setup:pick", group: "decide", tone: "p"/);
  assert.match(src, /\.\.\.fixRow, \.\.\.pickRow\]/);
  assert.doesNotMatch(src, /Microsoft 365 is one sign-in/);
  assert.match(src, /mail\[0\]\?\.title/);
});

test("setup's filled move is the lit one on the row: the dock passes it as the advice while setup is up", async () => {
  const { rowOf } = await import("../src/actionRow.js");
  const v = (id, extra = {}) => ({ id, group: "decide", tone: "s", label: id, ...extra });
  const list = [v("setup:back", { group: "next" }), v("setup:next", { tone: "p", disabled: true }), v("setup:pick", { tone: "p", label: "Connect Outlook mail" })];
  const r = rowOf({ ref: "", list }, { id: "setup:pick" });
  assert.deepEqual([...r.decide, ...r.agent].filter((x) => x.tone === "p").map((x) => x.id), ["setup:pick"]);
  assert.deepEqual([...rowOf({ ref: "", list }).decide].filter((x) => x.tone === "p"), [], "nothing named: nothing lit");
  const view = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
  assert.match(view, /<ActionRow advised=\{shownAdvice \|\| noneSaid \|\| setupLit\} \/>/);
});

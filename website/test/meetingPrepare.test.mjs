// PREPARE ON A MEETING (the owner, 2026-10-25: "add prepare that creates agent to research about person and topic through your mails"):
// the row's button beside Next, named by buttons.json, grouped with the agent's verbs - so on a narrow row it folds behind the ▾ and
// Next never does. Its press is the ordinary proposal road (runChip -> proposeDirect, concierge.AUTO), never a road of its own.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { label, hint, liveVerb } from "../src/buttons.js";
import { typeOf, phoneRow } from "../src/actionRow.js";

test("Prepare is a button of the one list, and the old Prep me stays gone", () => {
  assert.equal(label("prepare"), "Prepare");
  assert.match(hint("prepare"), /writes to nobody/);
  assert.equal(liveVerb("prep"), null);
});

test("on the row it is an agent's verb, and a phone row keeps Next apart from it", () => {
  assert.equal(typeOf({ id: "w:prepare" }), "agent");
  const prep = { id: "w:prepare", group: "decide", tone: "s", label: "Prepare" };
  const ph = phoneRow({ decide: [prep], agent: [], more: [] });
  assert.deepEqual(ph.shown, [prep]);
});

test("the card itself draws no second Prepare and calls no road of its own", () => {
  const cards = fs.readFileSync(new URL("../src/assistantCards.jsx", import.meta.url), "utf8");
  const meeting = cards.slice(cards.indexOf("export function MeetingCard"), cards.indexOf("export function ReportCard"));
  assert.doesNotMatch(meeting, /calendar\/prepare|verb: "prepare"|onClick=\{[^}]*prepare/);
});

// ...and ON THE TABLE it is a task's three sections, as every other row is (the owner, 2026-11-02: "this should be in same view as all other
// tasks with buttons to send to agent so i can prep for it"): Came from holds the invite, its moves are the row's on its panes
test("a meeting on the table opens in a task's three sections, its Send to agent the one agent box", () => {
  const cards = fs.readFileSync(new URL("../src/assistantCards.jsx", import.meta.url), "utf8");
  const meeting = cards.slice(cards.indexOf("export function MeetingCard"), cards.indexOf("export function ReportCard"));
  assert.match(meeting, /export function MeetingCard\(\{ card, table = null \}\)/);
  assert.match(meeting, /<ItemSections kind="meeting" itemKey=\{card\.key\} label="Meeting" height=\{table\} about="from" lays/);
  assert.match(meeting, /data-tq-meeting-from=""[\s\S]*\["When", when\], \["With", who\.join\(", "\)\], \["Where", e\.where\]/);
  assert.doesNotMatch(meeting, /<AgentAsk|TextField/, "no box of its own - the row's Send to agent opens the one every item opens");
  const view = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  assert.match(view, /meeting: <MeetingCard card=\{c\} onDone=\{actions\.done\} onOpenTask=\{actions\.openTask\} table=\{table\} \/>/);
  assert.match(view, /agentOn\.item\.kind === "meeting" \? "It gets the meeting: when, who, where and what the invite says\."/);
});

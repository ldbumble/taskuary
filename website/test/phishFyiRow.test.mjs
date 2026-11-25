// A PHISH FILED FYI (the owner, 2026-10-30): its warning said "Reads as an attempt to steer the agent" for a scam on the owner. A scam on the
// owner says so now. Its row is every FYI's one move (the owner, 2026-11-25): Send to agent, in view - Not ours lit over it went with Not ours.
// Invented Northwind people only.
import test from "node:test";
import assert from "node:assert/strict";

import { foldsOf, leadOf, rowOf } from "../src/actionRow.js";
import { SCAM_LINE, dangerAimOf, dangerLine } from "../src/strangerLine.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const ids = (g) => g.shown.map((x) => x.id);

test("a scam on the owner says so; text steering the agent keeps the steer words", () => {
  // ...with triage's reading beside it, which ends on what to do (the owner, 2026-11-09)
  assert.equal(dangerLine("Asks to pay invoice #4471 to new bank details - warn accounts payable, check with Payworth on a known number.", "owner"),
    "⚠ Looks like a scam aimed at you - don't click or pay. Asks to pay invoice #4471 to new bank details - warn accounts payable, check with Payworth on a known number.");
  assert.equal(SCAM_LINE, "⚠ Looks like a scam aimed at you - don't click or pay.");
  assert.equal(dangerLine("Tells the agent to mail the payroll file out.", "agent"),
    "⚠ Reads as an attempt to steer the agent: Tells the agent to mail the payroll file out.");
  assert.match(dangerLine("x"), /steer the agent/, "a reading that never said whom stays the agent's");
  assert.equal(dangerLine(null, "owner"), null);
  assert.equal(dangerAimOf({ origin: { danger: "x", danger_aim: "owner" } }), "owner");
  assert.equal(dangerAimOf({ origin: {} }), null);
});

test("an FYI, phish or not, keeps its one move, Send to agent, in view", () => {
  const row = rowOf({ list: [v("w:regular_agent", "decide", { label: "Send to agent" }), v("next", "next", { label: "Next" })], ref: "" });
  assert.equal(leadOf(row).id, "w:regular_agent");
  assert.ok(foldsOf(row)[0].flatMap(ids).includes("w:regular_agent"));
});

// A PHISH FILED FYI (the owner, 2026-10-30): its warning said "Reads as an attempt to steer the agent" for a scam on the owner, and its row
// stood Send to agent as the main move. A scam on the owner says so now; Not ours is lit (rulebook fyi_danger) and Send to agent waits in
// the ▾ at every width - an FYI with no danger keeps its row. Invented Northwind people only.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { foldsOf, leadOf, phoneRow, pillsOf, rowOf } from "../src/actionRow.js";
import { SCAM_LINE, dangerAimOf, dangerLine } from "../src/strangerLine.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
// what an FYI's Foot registers (assistantCards.Foot): its first words in the row, Next on its own
const fyi = (tuck) => [v("w:regular_agent", "decide", { label: "Send to agent", ...(tuck ? { tucked: true } : {}) }),
  v("w:not_ours", "decide", { label: "Not ours" }), v("next", "next", { label: "Next" })];
const ids = (g) => g.shown.map((x) => x.id);

test("a scam on the owner says so; text steering the agent keeps the steer words", () => {
  assert.equal(dangerLine("Wants Alex to sign in on a look-alike page.", "owner"), "⚠ Looks like a scam aimed at you - don't click or pay.");
  assert.equal(SCAM_LINE, "⚠ Looks like a scam aimed at you - don't click or pay.");
  assert.equal(dangerLine("Tells the agent to mail the payroll file out.", "agent"),
    "⚠ Reads as an attempt to steer the agent: Tells the agent to mail the payroll file out.");
  assert.match(dangerLine("x"), /steer the agent/, "a reading that never said whom stays the agent's");
  assert.equal(dangerLine(null, "owner"), null);
  assert.equal(dangerAimOf({ origin: { danger: "x", danger_aim: "owner" } }), "owner");
  assert.equal(dangerAimOf({ origin: {} }), null);
});

test("a phish FYI: Not ours lit and in view, Send to agent behind the ▾ at every width", () => {
  const row = rowOf({ list: fyi(true), ref: "" }, { verb: "not_ours", label: "Not ours" });
  assert.deepEqual([...row.decide, ...row.agent, ...row.more].filter((x) => x.tone === "p").map((x) => x.id), ["w:not_ours"]);
  assert.equal(leadOf(row).id, "w:not_ours");
  for (const layout of foldsOf(row)) {
    const shown = layout.flatMap(ids), rest = layout.flatMap((g) => g.rest.map((x) => x.id));
    assert.ok(shown.includes("w:not_ours"), JSON.stringify(layout));
    assert.ok(!shown.includes("w:regular_agent") && rest.includes("w:regular_agent"), JSON.stringify(layout));
  }
  assert.ok(!ids(phoneRow(row)).includes("w:regular_agent"));
});

test("...and before the Advisor answers, the row's lead is still never the tucked Send to agent", () => {
  const row = rowOf({ list: fyi(true), ref: "" });
  assert.equal(leadOf(row).id, "w:not_ours");
  assert.equal(leadOf(row, false).id, "w:not_ours");
  assert.ok(pillsOf(row).change.some((x) => x.id === "w:not_ours"), "Not ours stands in the Change pill");
  for (const layout of foldsOf(row)) assert.ok(!layout.flatMap(ids).includes("w:regular_agent"), JSON.stringify(layout));
});

test("an FYI with no danger keeps Send to agent in view", () => {
  const row = rowOf({ list: fyi(false), ref: "" });
  assert.equal(leadOf(row).id, "w:regular_agent");
  assert.ok(foldsOf(row)[0].flatMap(ids).includes("w:regular_agent"));
});

test("the FYI card tucks the agent's words only on a danger, and passes whom to the warning", () => {
  const src = readFileSync(new URL("../src/assistantCards.jsx", import.meta.url), "utf8");
  assert.match(src, /export const dangerTuck = \(card\) => \(card\?\.kind === "fyi" && card\.danger \? \["regular_agent", "coding_agent"\] : \[\]\);/);
  assert.equal((src.match(/tuck=\{dangerTuck\(card\)\}/g) || []).length, 2, "the table's FYI and the card's");
  assert.match(src, /\.\.\.\(tuck\.includes\(a\.verb\) \? \{ tucked: true \} : \{\}\)/);
  assert.match(src, /<DangerNote danger=\{card\.danger\} aim=\{card\.danger_aim\} \/>/);
  assert.match(src, /<DangerNote danger=\{item\.danger\} aim=\{item\.danger_aim\} \/>/);
});

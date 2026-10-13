import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseDigest } from "../src/digestText.js";

test("a successful digest keeps emoji sections and turns their items into section lists", () => {
  const got = parseDigest("🚨 Errors\n1. Payroll import failed.\n\n📅 Meetings today\n1. 9:00 — Standup\n2. 2:00 — Budget\n");
  assert.equal(got.error, "");
  assert.deepEqual(got.sections.map((s) => s.title), ["🚨 Errors", "📅 Meetings today"]);
  assert.deepEqual(got.sections[1].items, ["9:00 — Standup", "2:00 — Budget"]);
});

test("a failed digest leads with the failure and keeps raw evidence explicitly unreviewed", () => {
  const got = parseDigest("(AI summary failed: Azure returned 500)\n\nNOW: Tuesday 15 September\n\nMEETINGS TODAY:\n  9:00 · Standup · with Sam\n\nTHEIR ASKS YOU HAVE NOT ANSWERED (internal explanation):\n  Dana asked for the budget\n");
  assert.match(got.error, /Azure returned 500/);
  // the owner reads the cause in plain words first; the AI's own error is the detail beneath it
  assert.equal(got.plain, "The AI did not answer, so this morning's digest could not be written.");
  assert.equal(got.meta, "Tuesday 15 September");
  assert.deepEqual(got.sections.map((s) => s.title), ["📅 Meetings today", "🙋 People want"]);
  assert.equal(got.sections[1].items[0], "Dana asked for the budget");
  const component = readFileSync(fileURLToPath(new URL("../src/DigestText.jsx", import.meta.url)), "utf8");
  assert.match(component, /digest\.plain/);
  assert.match(component, /component="ol"/);
  assert.match(component, /Show unreviewed source data/);
  // ...and a way on: the digest written again, and the connection that would fix it
  assert.match(component, /Try again/);
  assert.match(component, /#connector=/);
});

test("no AI connected says so, in words", () => {
  const got = parseDigest("(AI prompt set, but no active AI connector - Connections → AI)\n\nNOW: Monday\n");
  assert.equal(got.plain, "No AI is connected, so this morning's digest could not be written.");
  assert.equal(parseDigest("📅 Meetings today\n1. 9:00 — Standup\n").plain, "");
});

test("a brief is the model's words: the evidence filed under it never merges into its sections", () => {
  const got = parseDigest("🙋 People want\n1. Erin needs your decision on the export.\n\n🚀 In flight\n1. TQ-0042 is in progress.\n\n--- raw data ---\nNOW: Tuesday\n\nTHEIR ASKS YOU HAVE NOT ANSWERED (their last word wants something):\n  Erin Blake asked Mon re \"Export\"\n\nNOT JUDGED (triage failed on these - while any are\nhere, never say nobody is waiting on you):\n  Ray Colton wrote Tue re \"PR\"\n");
  assert.deepEqual(got.sections.map((s) => s.title), ["🙋 People want", "🚀 In flight"]);
  assert.deepEqual(got.sections[0].items, ["Erin needs your decision on the export."]);
  assert.equal(got.meta, "");
});

test("a failed digest's wrapped block explanations are headings, never numbered items", () => {
  const got = parseDigest("(AI summary failed: timeout)\n\nNOW: Tuesday\n\nASKS YOUR STANDING VERDICTS ALREADY COVER (you ruled the topic is not yours, so these are NOT \"People want\"\nand rank below everything above; only a NEW ask outranks the verdict named on its line):\n  Gail asked about refunds\n\nNOT JUDGED (triage failed on these or has not run - while any are\nhere, never say nobody is waiting on you):\n  Ray Colton wrote Tue re \"PR\"\n\nWHAT ARRIVED (xN = that many alike):\n- x2 [ignored] vendor.example: \"Vendor create\"\n");
  assert.deepEqual(got.sections.map((s) => [s.title, s.items]), [
    ["📌 Asks your verdicts cover", ["Gail asked about refunds"]],
    ["❔ Not judged yet", ["Ray Colton wrote Tue re \"PR\""]],
    ["📥 What arrived", ["x2 [ignored] vendor.example: \"Vendor create\""]],
  ]);
});

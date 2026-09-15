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
  assert.equal(got.meta, "Tuesday 15 September");
  assert.deepEqual(got.sections.map((s) => s.title), ["📅 Meetings today", "🙋 People want"]);
  assert.equal(got.sections[1].items[0], "Dana asked for the budget");
  const component = readFileSync(fileURLToPath(new URL("../src/DigestText.jsx", import.meta.url)), "utf8");
  assert.match(component, /🚨 Errors/);
  assert.match(component, /component="ol"/);
  assert.match(component, /Show unreviewed source data/);
});

// "IS IT WORKING?" (the owner, 2026-10-22): the server's counts drawn as a table - numbers, and nothing said about them.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { workingCell, workingTable } from "../src/workingNumbers.js";

const w = (days, d, t, a) => ({ days, drafts: d, triage: t, agents: a });
const WINS = [w(7, { sent: 12, unedited: 8, edited: 3, redrafted: 1 }, { verdicts: 40, overturned: 2 }, { results: 0, accepted: 0, continued: 0, waiting: 0 }),
  w(30, { sent: 30, unedited: 30, edited: 0, redrafted: 0 }, { verdicts: 90, overturned: 0 }, { results: 5, accepted: 3, continued: 1, waiting: 1 })];

test("a cell is the count and its non-zero parts", () => {
  assert.equal(workingCell(12, [[8, "as drafted"], [3, "edited"], [1, "redrafted"]]), "12: 8 as drafted · 3 edited · 1 redrafted");
  assert.equal(workingCell(30, [[30, "as drafted"], [0, "edited"]]), "30: 30 as drafted");
  assert.equal(workingCell(0, [[0, "x"]]), "none");
});

test("three rows - drafts, triage, agent results - one cell per window", () => {
  const t = workingTable(WINS);
  assert.deepEqual(t.map((r) => r.label), ["Drafts sent", "Triage calls", "Agent results"]);
  assert.deepEqual(t[1].cells, ["40: 38 stood · 2 overturned", "90: 90 stood"]);
  assert.deepEqual(t[2].cells, ["none", "5: 3 marked done · 1 continued · 1 waiting on you"]);
  assert.deepEqual(workingTable(null), t.map((r) => ({ label: r.label, cells: [] })));
});

test("the Audit page draws it under its own heading, between the chain and the history", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/SettingsView.jsx", import.meta.url)), "utf8");
  assert.match(view, /api\.get\("\/api\/working"\)/);
  assert.match(view, /name=\{AUDIT_SECTIONS\[1\]\} \/><\/Box>\s*<WorkingNumbers \/>/);
});

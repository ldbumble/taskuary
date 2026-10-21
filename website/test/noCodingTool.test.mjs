import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// NO CODING TOOL CHOSEN, NO START (owner-approved, 2026-10-21, R3): the live-session picker was a blank box and Send to coding agent
// started a tool the owner never chose
const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("a coding picker with no tool says Pick a coding tool first, with Connect one, in place of the blank box", () => {
  const ui = src("ui.jsx");
  // ...on the server's own fact (agents.coding_ready, served by /api/agents) - the one terminal.start_on_task refuses on
  assert.match(ui, /if \(coding && brainsRead && !codingReady\) return <NoCodingTool \/>/);
  assert.match(ui, /setCodingReady\(data\.coding_ready/);
  assert.match(ui, /export const NO_CODING_TOOL = "Pick a coding tool first"/);
  assert.match(ui, /Connect one<\/Button>/);
});

test("Send to coding agent stays off with no coding tool, on the New sheet and the task page", () => {
  assert.match(src("NewSheet.jsx"), /const canGo = hasAbout && !noCodingTool/);
  assert.match(src("TaskPage.jsx"), /runPics\.busy \|\| !agentsRead \|\| !codingReady\}/);
});

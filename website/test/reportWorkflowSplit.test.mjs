import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { isWorkflowConfig } from "../src/sourceShape.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("Reports has separate report and workflow shelves", () => {
  const view = read("ReportsView.jsx");
  const ui = read("ui.jsx");
  assert.match(view, /section: "Reports"/);
  assert.match(view, /section: "Routines"/);
  assert.match(view, /label: "\+ New routine"/);
  assert.match(ui, /if \(it\.section\)/);
});

test("read versus write decides the shelf, not whether an agent runs it", () => {
  assert.equal(isWorkflowConfig({ type: "agent", prompt: "Fetch GitHub Trending" }), false);
  assert.equal(isWorkflowConfig({ type: "agent", access: "read", prompt: "Summarize it" }), false);
  assert.equal(isWorkflowConfig({ type: "agent", access: "write", prompt: "Update the records" }), true);
  assert.equal(isWorkflowConfig({ type: "zoho_monthly_invoices" }), true);
  const view = read("ReportsView.jsx");
  assert.match(view, /Report · read-only — this agent can retrieve data but cannot change it/);
  assert.match(view, /Routine · write access — this agent may change data/);
});

// ...the builder is the Assistant's to fill now (2026-10-30): the composer is a field of the Reports view it sets, never a box on the page
test("the workflow shelf has its own conversational AI builder", () => {
  const view = read("ReportsView.jsx");
  assert.match(view, /kind === "workflow" \? "\/api\/workflows\/compose"/);
  assert.match(view, /"Describe the routine you want"/);
  assert.match(view, /useViewExtras\("reports", \{ fields: \[\{ key: "describe"/);
  assert.match(view, /<SetupWithAi kind="workflow"/);
});

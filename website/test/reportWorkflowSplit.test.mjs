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

// ...the routine is built on its own page by Set up with AI (taskuary/build.py, 2026-11-13) - no describe field for the chat to fill
test("the workflow shelf has its own AI builder, on its page", () => {
  const view = read("ReportsView.jsx");
  assert.match(view, /<SetupWithAi kind="workflow"/);
  assert.doesNotMatch(view, /key: "describe"/);
});

// COPY SLIPS (the product audit, 2026-11-08): one word for one thing, no internal words on a screen
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("Reports says routines, a data card has no template line, profiles live in Settings, the Hub names no agent's tool", () => {
  assert.match(src("ReportsView.jsx"), /plural\(workflowSources\.length, "routine"\)[^`]*routines act/);
  const cv = src("ConnectorsView.jsx");
  assert.doesNotMatch(cv, /\{meta\.desc\} The connection only/); assert.doesNotMatch(cv, /ships at authority READ/);
  assert.match(src("AgentsPanel.jsx"), />Manage profiles in Settings</);
  const hub = src("HubView.jsx");
  assert.doesNotMatch(hub, /`agent \$\{p\.Author/); assert.match(hub, /byOwner\(p\.Author\) \? \(\s*<Typography[^>]*>posted by hand/);
});

test("What the assistant changed lists only what it changed - a setting, a report, a connection", () => {
  const sv = src("SettingsView.jsx");
  assert.match(sv, /const CHANGED = \["setting", "source", "connector"\];/);
  assert.match(sv, /filter\(\(r\) => CHANGED\.includes\(r\.entity\)\)/);
});

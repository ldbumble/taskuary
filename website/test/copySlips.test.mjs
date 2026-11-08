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

// SAID ONCE (the product audit, 2026-11-08): the to-do's paragraph under What came in and again as The ask; "+ New playbook" twice on its
// shelf; a back crumb under the Phone & chats chip that is already lit
test("an ask that is its message's words, a second New playbook and a single page's back crumb are each drawn once", async () => {
  const { askInBody } = await import("../src/taskLayout.js");
  const body = "Welcome to the demo. Northwind, its people and their mail are invented, and nothing you press here reaches anyone.";
  assert.equal(askInBody(body, `${body}\n\nAlex`), true); assert.equal(askInBody("Book the room", body), false);
  assert.match(src("TaskPage.jsx"), /!\(sourceCount === 1 && askInBody\(askText, opener\?\.ReadText \|\| opener\?\.BodyText\)\)/);
  assert.match(src("ReportsView.jsx"), /<NewPlaybook [^>]*button=\{false\}/);
  assert.match(src("PlaybookShelf.jsx"), /\{button && <Button size="small" variant="outlined"/);
  assert.match(src("SettingsView.jsx"), /noBack: section === PHONE_PAGE \|\| section === "you"/);
  assert.match(src("CanvasBrowse.jsx"), /\{!noBack && <Box sx=\{\{ display: "flex", alignItems: "center", gap: 1\.25, px: 1\.75/);
});

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { agentAssignee, assignedAgent, assigneeLabel } from "../src/agentIdentity.js";

test("agent ownership storage syntax never leaks into the UI", () => {
  assert.equal(agentAssignee("Atlas"), "agent:Atlas");
  assert.equal(assignedAgent("agent:Atlas"), "Atlas");
  assert.equal(assigneeLabel("agent:Atlas"), "Taskuary", "the profile is instructions, never who works it");
  assert.equal(assigneeLabel("Erin Blake"), "Erin Blake", "a person keeps their name");
  assert.equal(assigneeLabel("owner"), "you");
  assert.equal(assigneeLabel(""), "unassigned");
});

// PROFILE NAMES HIDDEN IN SETTINGS (the owner, 2026-10-29), as on every other screen (kinds.json `shown_`): Settings' mail pick reads
// Taskuary and its instructions. The task header's Assigned to picker is GONE (the owner, 2026-11-01): who works a task is decided only in
// the Agent section - Send to agent / Start - and the server's Assignee is set from there
test("the task header has no Assigned to menu and Settings names no profile as a worker", () => {
  const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
  const page = read("TaskPage.jsx"), settings = read("SettingsView.jsx");
  assert.ok(!page.includes('what: "assign"') && !page.includes('pick?.what === "assign"'), "the Assigned to menu is back");
  assert.doesNotMatch(page, /Assigned to ·|id: "assign"/);
  assert.doesNotMatch(page, /who it is assigned to/, "a Change hover still offers the assignee");
  const pick = settings.slice(settings.indexOf('if (m.type === "profile") return ('), settings.indexOf('if (m.type === "agents")'));
  assert.match(pick, /renderValue=\{\(v\) => \(v \? AGENT_SHOWN : "nobody - leave it for me to pick"\)\}/);
  assert.match(pick, /\{AGENT_SHOWN\}\s*<Box component="span"[^>]*>\{instructionsHint\(n\)\}<\/Box>/);
  assert.doesNotMatch(pick, />\{n\}<\/MenuItem>/, "a profile never stands alone as the choice");
  const knob = JSON.parse(readFileSync(new URL("../../taskuary/settings_schema.json", import.meta.url), "utf8")).knobs.default_profile;
  assert.doesNotMatch(`${knob.desc} ${knob.help}`, /\bworker\b/, "the setting's words name no worker but Taskuary");
});

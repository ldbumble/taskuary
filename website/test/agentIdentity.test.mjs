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

// PROFILE NAMES HIDDEN IN SETTINGS AND THE ASSIGNED TO PICKER (the owner, 2026-10-29), as on every other screen (kinds.json `shown_`):
// the picker is who - unassigned, you, Taskuary - with the profile on hover; Settings' mail pick reads Taskuary and its instructions
test("the Assigned to picker offers one Taskuary row and Settings names no profile as a worker", () => {
  const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
  const page = read("TaskPage.jsx"), settings = read("SettingsView.jsx");
  const at = page.indexOf('{pick?.what === "assign" && [');
  const picker = page.slice(at, page.indexOf("</Menu>}", at));
  assert.match(picker, /\["", "unassigned"\], \["owner", "you"\], \.\.\.\(asProfile \? \[\[agentAssignee\(asProfile\), AGENT_SHOWN\]\] : \[\]\)/);
  assert.doesNotMatch(picker, /agents\.map\(/, "no row per profile");
  assert.match(picker, /title=\{instructionsHint\(assignedAgent\(v\)\) \|\| undefined\}/, "the profile is told on hover");
  assert.match(page, /const asProfile = runRole \|\| ownProfile \|\| "";/);
  const pick = settings.slice(settings.indexOf('if (m.type === "profile") return ('), settings.indexOf('if (m.type === "agents")'));
  assert.match(pick, /renderValue=\{\(v\) => \(v \? AGENT_SHOWN : "nobody - leave it for me to pick"\)\}/);
  assert.match(pick, /\{AGENT_SHOWN\}\s*<Box component="span"[^>]*>\{instructionsHint\(n\)\}<\/Box>/);
  assert.doesNotMatch(pick, />\{n\}<\/MenuItem>/, "a profile never stands alone as the choice");
  const knob = JSON.parse(readFileSync(new URL("../../taskuary/settings_schema.json", import.meta.url), "utf8")).knobs.default_profile;
  assert.doesNotMatch(`${knob.desc} ${knob.help}`, /\bworker\b/, "the setting's words name no worker but Taskuary");
});

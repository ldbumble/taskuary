import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("task and attachment actions use keyboard-operable buttons", () => {
  const wall = read("AgentWall.jsx");
  const attachments = read("Attachments.jsx");
  const taskPage = read("TaskPage.jsx");

  assert.match(wall, /<Typography component="button" type="button"[^>]+onClick=\{\(\) => onOpenTask\?\.\(n\.TaskId\)\}/);
  assert.match(attachments, /<Typography variant="caption" component="button" type="button"[^>]+onClick=\{fetchNow\}/);
  assert.match(attachments, /<Box key=\{a\.id\} component="button" type="button"[^>]+onClick=\{\(\) => setBig\(a\)\}/);
  assert.match(taskPage, /<Box component="button" type="button" onClick=\{\(\) => \{ const next = diffScope === "task" \? "checkout" : "task";/);
});

test("AI defaults navigation links are keyboard-operable buttons", () => {
  const aiDefaults = read("AiDefaults.jsx");
  assert.ok(aiDefaults.includes('<Typography component="button" type="button" variant="caption" onClick={() => onGo(slot.owner_link)}'));
  assert.ok(aiDefaults.includes('<Typography component="button" type="button" variant="body2" onClick={() => onGo("connectors")}'));
});

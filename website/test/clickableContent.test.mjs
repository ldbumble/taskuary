import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("task and attachment actions use keyboard-operable buttons", () => {
  const wall = read("AgentWall.jsx");
  const attachments = read("Attachments.jsx");

  assert.match(wall, /<Typography component="button" type="button"[^>]+onClick=\{\(\) => onOpenTask\?\.\(n\.TaskId\)\}/);
  assert.match(attachments, /<Typography variant="caption" component="button" type="button"[^>]+onClick=\{fetchNow\}/);
  assert.match(attachments, /<Box key=\{a\.id\} component="button" type="button"[^>]+onClick=\{\(\) => setBig\(a\)\}/);
});

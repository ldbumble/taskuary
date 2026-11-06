import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// NO "Taskuary answered" OVER A CHAT (the owner, 2026-11-05)
test("a chat has no heading line of its own", () => {
  assert.match(read("TaskPage.jsx"), /\{!codeRun && !chatPane && <Box ref=\{agentHead\} data-tq-agent-head=""/);
});

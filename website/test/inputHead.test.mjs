import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// AN INPUT IS ICON, WHO, WHEN (the owner, 2026-11-05: drop "· sent to Taskuary" - every input goes to it)
test("no input bubble says it was sent to the agent", () => {
  const ws = read("GeneralWorkspace.jsx");
  assert.doesNotMatch(ws, /`sent to \$\{agent\}`/);
  assert.match(ws, /from \$\{x\.who \|\| "someone"\}`\];/);
  assert.match(ws, /\{\[\.\.\.headOf\(x\), stamp\]\.filter\(Boolean\)\.join\(" · "\)\}/);
});

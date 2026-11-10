// REMIND ME WORKS LIKE SEND (the owner, 2026-11-10: "remind me should be like send. it will show on the card what happened"): it warned and
// refused while an agent's session was open - now the day is set whatever the agent is doing, and the server puts the agent to rest (remind.rest)
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("the picker offers its days whatever the agent is doing - no warning, no live flag on any door", () => {
  const picker = read("RemindMe.jsx");
  assert.doesNotMatch(picker, /\blive\b|still open on this task/);
  for (const f of ["TaskPage.jsx", "AssistantView.jsx", "gameItem.jsx"]) assert.doesNotMatch(read(f), /<Remind(Me|Picker) [^\n]*live=|agentOpen\(/, f);
});

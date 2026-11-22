// A BUTTON THAT CANNOT WORK IS GREYED, ITS REASON IN THE HOVER (the owner, 2026-10-22): with no AI connected Send to agent, Try
// again, Run another agent, Re-plan and a step's Send to agent were all pressable, each only to fail; and a goal came pre-set to
// Plan it, which nothing could plan. One check, capabilities.cannotStart, for both roads - coding keeps R3's own words.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
// capabilities.js imports the page's api client; its pure rule is lifted from the source and run here
const { cannotStart, NO_AI_WHY, NO_CODING_TOOL } = (() => {
  const c = read("capabilities.js"), one = (n) => c.slice(c.indexOf(`export const ${n} =`), c.indexOf(";\n", c.indexOf(`export const ${n} =`)) + 1);
  const src = ["aiFor", "NO_AI_WHY", "NO_CODING_TOOL", "cannotStart"].map(one).join("\n").replace(/export const /g, "const ");
  return new Function(`${src}\nreturn { cannotStart, NO_AI_WHY, NO_CODING_TOOL };`)();
})();

test("cannotStart: no AI greys the general road; no coding tool greys only coding; an unread list greys nothing", () => {
  assert.equal(cannotStart({ ai: false }), NO_AI_WHY);
  assert.equal(cannotStart({ ai: false }, { coding: true, read: true, codingReady: true }), "", "a coding agent runs its own tool, no AI needed");
  assert.equal(cannotStart({ ai: false }, { coding: true, read: true, codingReady: false }), NO_CODING_TOOL);
  // ...the general road asks the server's one answer for general work, never triage's nor a list of its own (2026-11-19)
  assert.equal(cannotStart({ ai: true, ai_for: { general: false } }, { read: true }), NO_AI_WHY, "triage has an AI, general work has none");
  assert.equal(cannotStart({ ai: false, ai_for: { general: true } }, { read: true }), "", "general work has one though triage has none");
  assert.equal(cannotStart({ ai: true }, { read: false }), "", "not read yet is not a no");
  assert.equal(cannotStart({ ai: true }, { coding: true, read: true, codingReady: false }), NO_CODING_TOOL);
  assert.equal(cannotStart({ ai: true }, { coding: true, read: true, brains: [], codingReady: true }), "", "coding asks its tool, not general_brains");
  assert.equal(NO_CODING_TOOL, "Pick a coding tool first");
});

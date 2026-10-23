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
  const src = ["NO_AI_WHY", "NO_CODING_TOOL", "cannotStart"].map(one).join("\n").replace(/export const /g, "const ");
  return new Function(`${src}\nreturn { cannotStart, NO_AI_WHY, NO_CODING_TOOL };`)();
})();

test("cannotStart: no AI greys the general road; no coding tool greys only coding; an unread list greys nothing", () => {
  assert.equal(cannotStart({ ai: false }), NO_AI_WHY);
  assert.equal(cannotStart({ ai: false }, { coding: true, read: true, codingReady: true }), "", "a coding agent runs its own tool, no AI needed");
  assert.equal(cannotStart({ ai: false }, { coding: true, read: true, codingReady: false }), NO_CODING_TOOL);
  assert.equal(cannotStart({ ai: true }, { read: true, brains: [] }), NO_AI_WHY, "general_brains read and empty is no AI");
  assert.equal(cannotStart({ ai: true }, { read: false, brains: [] }), "", "not read yet is not a no");
  assert.equal(cannotStart({ ai: true }, { read: true, brains: [{ pick: "cli:codex" }] }), "");
  assert.equal(cannotStart({ ai: true }, { coding: true, read: true, codingReady: false }), NO_CODING_TOOL);
  assert.equal(cannotStart({ ai: true }, { coding: true, read: true, brains: [], codingReady: true }), "", "coding asks its tool, not general_brains");
  assert.equal(NO_CODING_TOOL, "Pick a coding tool first");
});

test("the task page greys every agent start on that one check, the reason in the hover", () => {
  const p = read("TaskPage.jsx");
  assert.match(p, /noAiWhy = runWhy\(false\)/);
  for (const id of ["run-another", "continue"]) assert.match(p, new RegExp(`id: "${id}"[^\\n]*disabled: [^\\n]*!!noAiWhy, why: noAiWhy`), id);
  // ...each of them opening the agent box, never starting at the press (the owner, 2026-10-23)
  assert.equal((p.match(/disabled: !!startingAgent \|\| !!noAiWhy, why: noAiWhy, run: openBox/g) || []).length, 3, "send-general and both start-agents");
  assert.match(p, /disabled=\{!!startingAgent \|\| runPics\.busy \|\| !!noAiWhy\}/, "the Run another agent form's start");
  assert.match(p, /!agentsRead \|\| !!runWhy\(true\)\}/, "the coding start reads the same check");
  assert.match(p, /disabled=\{replanning \|\| !!noAiWhy\}/, "Re-plan");
});

test("a goal starts on Track it when no AI is connected, and follows the capability until the owner picks", () => {
  const s = read("NewSheet.jsx");
  assert.match(s, /useState\(!noAi\), planPicked = useRef\(false\)/);
  assert.match(s, /if \(!planPicked\.current\) setPlan\(!noAi\)/);
  assert.doesNotMatch(s, /\[plan, setPlan\] = useState\(true\)/);
});

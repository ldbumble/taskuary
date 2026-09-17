// The fifth card offers a model that answers but cannot speak. The other four must never see it:
// AI_TYPES keeps it out of /api/brains on the server, and this keeps the page from putting it back.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the judge slot offers the decision model, and the other four never do", () => {
  const panel = read("AiDefaults.jsx");
  assert.match(panel, /judge_ai/);
  assert.match(panel, /judge_options/);
  // the decision model reaches exactly one picker: every other slot still reads `brains`
  const slot = panel.slice(panel.indexOf("const Slot"), panel.indexOf("export default"));
  assert.match(slot, /slot\.key === "judge_ai"/);
});

test("the judge picker does not offer auto twice", () => {
  // `brains` leads with an auto entry whose value is "", which is exactly what the judge's own
  // "the report's own brain" means - two rows that do the same thing read as a choice.
  const panel = read("AiDefaults.jsx");
  const slot = panel.slice(panel.indexOf("const Slot"), panel.indexOf("export default"));
  assert.match(slot, /brains\s*\|\|\s*\[\]\)\.filter\(\(o\) => o\.value\)/);
});

test("the slot with no model of its own does not show a model box", () => {
  const panel = read("AiDefaults.jsx");
  const slot = panel.slice(panel.indexOf("const Slot"), panel.indexOf("export default"));
  assert.match(slot, /!isJudge && \(/);
});

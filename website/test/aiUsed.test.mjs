import test from "node:test";
import assert from "node:assert/strict";
import { tokens, took, usedLine, usedTotal } from "../src/aiUsed.js";

// THE TASK'S "AI USED" LINES (aiusage.for_task): each call in plain words; what nothing counted is left out, never said as 0
test("a call reads as its job, model, how hard, tokens and time", () => {
  assert.equal(usedLine({ what: "general work", model: "claude-sonnet-4-5", tier: "normal", tokens: 94000, seconds: 600, calls: 3 }),
    "general work · claude-sonnet-4-5 · normal · 94K tokens · 10m · 3 calls");
  assert.equal(usedLine({ what: "triage", model: "gemini-flash", tier: "as set", tokens: null, seconds: 1.4, calls: 1 }), "triage · gemini-flash · 1s");
});

test("the total, and the small numbers", () => {
  assert.equal(usedTotal({ calls: 4, tokens: 1250000, seconds: 3725 }), "4 calls · 1.3M tokens · 1h 2m");
  assert.equal(usedTotal({ calls: 0 }), "");
  assert.equal(tokens(950), "950"); assert.equal(tokens(null), ""); assert.equal(took(0.2), "<1s"); assert.equal(took(null), "");
});

test("a task's outputs folder named as a path is a link that opens it, any other path is not", async () => {
  const src = (await import("node:fs")).readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  const line = src.split("\n").find((l) => l.startsWith("export const isOutputsFolder"));
  const isOutputsFolder = eval(line.replace("export const isOutputsFolder =", "(").replace(/;\s*$/, "") + ")");
  assert.ok(isOutputsFolder(String.raw`C:\Users\alex\.taskuary\scratch\outputs\TQ-1348\ `, 1348));
  assert.ok(isOutputsFolder("~/.taskuary/scratch/outputs/TQ-0042", 42));
  assert.ok(!isOutputsFolder(String.raw`C:\Users\alex\.taskuary\scratch\outputs\TQ-1348`, 1349));
  assert.ok(!isOutputsFolder(String.raw`C:\Windows\System32`, 1348));
});

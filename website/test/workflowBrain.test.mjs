// A workflow runs on the general agents' brain unless it asks for a harder model or more effort - and only what that CLI takes is offered.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { effortChoices, keepEffort, modelChoices } from "../src/workflowBrain.js";

const claude = { said: "Claude Code · claude-opus-5-5", cli: "claude", efforts: ["low", "medium", "high", "xhigh", "max"],
  models: [{ id: "claude-opus-5-5", label: "Opus 5.5", efforts: ["low", "medium", "high", "xhigh", "max"] }, { id: "haiku", label: "haiku", efforts: [] }] };
const codex = { said: "OpenAI Codex CLI · its default model", cli: "codex", efforts: ["low", "medium", "high", "xhigh"],
  models: [{ id: "gpt-5.5", label: "GPT-5.5", efforts: ["low", "medium", "high", "xhigh"] }] };
const copilot = { said: "GitHub Copilot CLI · its default model", cli: "copilot", efforts: [], models: [{ id: "auto", label: "auto", efforts: [] }] };

test("the default is the general agents' brain, named, then the CLI's own models", () => {
  assert.deepEqual(modelChoices(claude).map((c) => c.value), ["", "claude-opus-5-5", "haiku"]);
  assert.equal(modelChoices(claude)[0].label, "Same as general agents (Claude Code · claude-opus-5-5)");
  assert.equal(modelChoices(claude)[1].label, "Opus 5.5 (claude-opus-5-5)");
  assert.deepEqual(modelChoices(null), []);
});

test("only the efforts the chosen model's CLI takes are offered", () => {
  assert.deepEqual(effortChoices(codex, "gpt-5.5").map((c) => c.value), ["", "low", "medium", "high", "xhigh"]);   // codex: no max
  assert.deepEqual(effortChoices(claude, "").map((c) => c.value), ["", "low", "medium", "high", "xhigh", "max"]);
  assert.deepEqual(effortChoices(claude, "haiku"), []);                                                             // haiku thinks at one level
  assert.deepEqual(effortChoices(copilot, ""), [], "no effort flag to spell: no Effort box");
  assert.equal(keepEffort(codex, "gpt-5.5", "max"), "");
  assert.equal(keepEffort(claude, "claude-opus-5-5", "max"), "max");
});

test("the editor carries Model and Effort on one row, fed by the brain endpoint", () => {
  const src = fs.readFileSync(new URL("../src/WorkflowEditor.jsx", import.meta.url), "utf8");
  assert.ok(src.includes('api.get("/api/workflows/brain")'));
  assert.ok(src.includes("modelChoices(brain)") && src.includes("effortChoices(brain, cfg.model)"));
  assert.ok(src.includes('model: e.target.value, effort: keepEffort(') && src.includes('set("effort"'), "a new model drops an effort it cannot take");
});

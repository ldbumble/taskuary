import test from "node:test";
import assert from "node:assert/strict";
import { normalizeBrainOptions } from "../src/brainOptions.js";

test("old profile-shaped brain rows collapse to one choice per CLI", () => {
  const rows = [
    { value: "", label: "auto" },
    { value: "cli:coder", label: "claude · coder", models: [] },
    { value: "cli:researcher", label: "claude · researcher", models: [] },
    { value: "cli:copilot", label: "copilot · copilot", models: [] },
  ];
  const models = {
    coder: { cli: "claude", choices: ["opus", "sonnet"] },
    researcher: { cli: "claude", choices: ["opus", "sonnet"] },
    copilot: { cli: "copilot", choices: ["auto", "gpt-5.4"] },
  };
  const got = normalizeBrainOptions(rows, models, ["cli:researcher"]);
  assert.deepEqual(got.map((r) => r.label), ["claude (your CLI)", "auto", "copilot (your CLI)"]);
  assert.equal(got[0].value, "cli:researcher");
  assert.deepEqual(got[2].models, ["auto", "gpt-5.4"]);
});

test("API connector choices are not rewritten", () => {
  const row = { value: "connector:7", label: "Azure OpenAI", models: [] };
  assert.deepEqual(normalizeBrainOptions([row]), [row]);
});

import test from "node:test";
import assert from "node:assert/strict";
import { normalizeBrainOptions } from "../src/brainOptions.js";

test("old profile-shaped brain rows collapse to one choice per CLI", () => {
  const rows = [
    { value: "", label: "auto" },
    { value: "cli:coding", label: "claude · coding", models: [] },
    { value: "cli:researcher", label: "claude · researcher", models: [] },
    { value: "cli:copilot", label: "copilot · copilot", models: [] },
  ];
  const models = {
    coding: { cli: "claude", choices: ["opus", "sonnet"] },
    researcher: { cli: "claude", choices: ["opus", "sonnet"] },
    copilot: { cli: "copilot", choices: ["auto", "gpt-5.4"] },
  };
  const got = normalizeBrainOptions(rows, models, ["cli:researcher"]);
  assert.deepEqual(got.map((r) => r.label), ["claude (on this computer)", "auto", "copilot (on this computer)"]);
  assert.equal(got[0].value, "cli:researcher");
  assert.deepEqual(got[2].models, ["auto", "gpt-5.4"]);
});

test("API connector choices are not rewritten", () => {
  const row = { value: "connector:7", label: "Azure OpenAI", models: [] };
  assert.deepEqual(normalizeBrainOptions([row]), [row]);
});

// THE CODING PICKER LISTS AI CARDS TOO (the owner, 2026-11-09: "fix the picker please. it should choose the correct one")
import { codingChoice, codingChoices } from "../src/brainOptions.js";
import { readFileSync } from "node:fs";

const opts = [
  { value: "cli:claude", key: "claude", kind: "cli", label: "Claude Code (on this computer)" },
  { value: "connector:7", connector: 7, kind: "card", label: "HIPAA AI · claude-sonnet-5-5" },
  { value: "connector:9", connector: 9, kind: "card", label: "Azure OpenAI · gpt-5" },
];

test("every CLI and every AI card is offered, and nothing chosen shows what the server will run", () => {
  const got = codingChoices({ options: opts, brains: ["claude"], codingPick: "connector:7" });
  assert.deepEqual(got.list.map((o) => o.label), ["Claude Code (on this computer)", "HIPAA AI · claude-sonnet-5-5", "Azure OpenAI · gpt-5"]);
  assert.equal(got.value, "connector:7");                  // the card chosen in Settings, not the first CLI
  assert.equal(codingChoices({ options: opts, codingPick: "cli:claude" }).value, "cli:claude");
});

test("a pick on the task wins, a CLI as `brain` and a card as `pick`", () => {
  assert.equal(codingChoices({ options: opts, brain: "claude", codingPick: "connector:7" }).value, "cli:claude");
  assert.equal(codingChoices({ options: opts, pick: "connector:9", codingPick: "cli:claude" }).value, "connector:9");
  assert.deepEqual(codingChoice("connector:9"), { brain: "", pick: "connector:9" });
  assert.deepEqual(codingChoice("cli:claude"), { brain: "claude", pick: "" });
});

test("a brain the task names that is gone stays named; an old server's CLI keys still list", () => {
  const gone = codingChoices({ options: opts, brain: "gemini" });
  assert.equal(gone.value, "cli:gemini"); assert.match(gone.list[0].label, /gemini · not connected/);
  assert.deepEqual(codingChoices({ brains: ["claude", "codex"] }).list.map((o) => o.value), ["cli:claude", "cli:codex"]);
});

test("the picker draws codingChoices' list and Settings draws the server's coding options", () => {
  const ui = readFileSync(new URL("../src/ui.jsx", import.meta.url), "utf8");
  assert.match(ui, /code\.list\.map\(\(o\) => \(\s*<MenuItem key=\{o\.value\} value=\{o\.value\} data-tq-coding-option/);
  assert.match(ui, /codingOptions: data\.coding_options \|\| \[\], codingPick: data\.coding_pick \|\| ""/);
});

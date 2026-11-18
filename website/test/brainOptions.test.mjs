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
  assert.deepEqual(got.map((r) => r.label), ["claude", "auto", "copilot"]);
  assert.equal(got[0].value, "cli:researcher");
  assert.deepEqual(got[2].models, ["auto", "gpt-5.4"]);
});

// ONE NAME PER AI (decided 2026-11-12): the server's name for a CLI is drawn as it comes - "Claude Code", never "claude (on this computer)"
test("a CLI keeps the one name the server gives it", () => {
  const got = normalizeBrainOptions([{ value: "cli:claude", label: "Claude Code" }, { value: "cli:codex", label: "OpenAI Codex CLI" }], { claude: { cli: "claude" }, codex: { cli: "codex" } });
  assert.deepEqual(got.map((r) => r.label), ["Claude Code", "OpenAI Codex CLI"]);
});

test("API connector choices are not rewritten", () => {
  const row = { value: "connector:7", label: "Azure OpenAI", models: [] };
  assert.deepEqual(normalizeBrainOptions([row]), [row]);
});

// THE CODING PICKER LISTS AI CARDS TOO (the owner, 2026-11-09: "fix the picker please. it should choose the correct one")
import { codingChoice, codingChoices } from "../src/brainOptions.js";
import { readFileSync } from "node:fs";

const opts = [
  { value: "cli:claude", key: "claude", kind: "cli", label: "Claude Code" },
  { value: "connector:7", connector: 7, kind: "card", label: "HIPAA AI · claude-sonnet-5-5" },
  { value: "connector:9", connector: 9, kind: "card", label: "Azure OpenAI · gpt-5" },
];

test("every CLI and every AI card is offered, and nothing chosen shows what the server will run", () => {
  const got = codingChoices({ options: opts, brains: ["claude"], codingPick: "connector:7" });
  assert.deepEqual(got.list.map((o) => o.label), ["Claude Code", "HIPAA AI · claude-sonnet-5-5", "Azure OpenAI · gpt-5"]);
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

// HAND THE TASK TO ANOTHER AI (the owner, 2026-11-18): every AI ready, each with its models, the one at work marked - greyed with its reason
// where there is nothing else to hand it to
test("the task's AI switch lists every ready AI and its models, the one at work marked", async () => {
  const { switchChoices } = await import("../src/brainOptions.js");
  const generalBrains = [{ pick: "cli:claude", label: "Claude Code", models: [{ id: "opus", label: "Opus" }] },
    { pick: "cli:codex", label: "Codex CLI", models: [{ id: "gpt-6.2", label: "gpt-6.2" }] }, { pick: "connector:4", label: "Azure OpenAI", models: [] }];
  const got = switchChoices({ generalBrains, current: "cli:claude", model: "opus" });
  assert.deepEqual(got.rows.map((r) => [r.pick, r.model, !!r.now]),
    [["cli:claude", "", false], ["cli:claude", "opus", true], ["cli:codex", "", false], ["cli:codex", "gpt-6.2", false], ["connector:4", "", false]]);
  assert.equal(got.said, "Claude Code · opus"); assert.equal(got.why, "");
  // a coding task: its CLIs (models from brain_models) and its AI cards; one not ready is no choice
  const coding = switchChoices({ coding: true, current: "cli:claude", brainModels: { codex: { models: [{ id: "gpt-6.2" }] } }, generalBrains,
    codingOptions: [{ value: "cli:claude", key: "claude", kind: "cli", label: "Claude Code", ready: true },
      { value: "cli:codex", key: "codex", kind: "cli", label: "Codex CLI", ready: true }, { value: "cli:gemini", key: "gemini", kind: "cli", label: "Gemini", ready: false }] });
  assert.deepEqual(coding.rows.map((r) => r.pick + "/" + r.model), ["cli:claude/", "cli:codex/", "cli:codex/gpt-6.2"]);
  assert.ok(coding.rows[0].now);
  // nothing else to hand it to: greyed, with the reason
  assert.match(switchChoices({ generalBrains: [{ pick: "cli:claude", label: "Claude Code" }], current: "cli:claude" }).why, /Only one AI is ready/);
  // the 2026-11-18 walk: one AI listed sixteen models - each AI shows its few, the one at work always, the rest folded under More models
  const many = Array.from({ length: 16 }, (_, i) => ({ id: `m${i}`, label: `Model ${i}` }));
  const long = switchChoices({ generalBrains: [{ pick: "cli:claude", label: "Claude Code", models: many }, { pick: "cli:codex", label: "Codex CLI", models: [] }],
    current: "cli:claude", model: "m9" });
  assert.deepEqual(long.rows.filter((r) => !r.more).map((r) => r.model), ["", "m0", "m1", "m2", "m9", ""]);
  assert.equal(long.rows.filter((r) => r.more).length, 12);
  assert.match(switchChoices({ generalBrains: [] }).why, /No AI is connected/);
});

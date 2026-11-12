// A repository dialog asks WHICH CLI, not which worker.
//
// Both shipped coding workers carry rules_doc "coding", so `coding` and `codex` are one job on two
// CLIs - and the menu listed them beside researcher, analyst, coordinator, marketer and trader,
// under a label promising "which CLI works it" (the owner, 2026-09-14: "for coding there is no need
// to choose profile. That's for general. Coding is the profile for coding sessions").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the coding picker filters to coding workers and names them by their CLI", () => {
  const ui = read("ui.jsx");
  const picker = ui.slice(ui.indexOf("export const AgentPicker"), ui.indexOf("export const timeAgo"));
  assert.match(picker, /kinds = \{\},\n\s+coding = false/);
  assert.match(picker, /\["coding", "cli"\]\.includes\(String\(kinds\[a\] \|\| ""\)\.toLowerCase\(\)\)/);
  // The brain layer (33e452f5) answered this question at the source instead of translating at the
  // menu: a coding picker now lists BRAINS, which already are CLIs, so the `cliOf` map this used to
  // assert on has nothing left to do. Same promise, one fewer indirection - and the choice it
  // writes is the brain, never the role, because every coding task's role is the coding profile.
  // ...and a brain the machine no longer has is still what this task NAMES: the list used to fall
  // back to brains[0], so filtering to installed brains would have shown a CLI nobody chose.
  // ...and a coding task runs on a CLI OR an AI card (2026-11-09): the list is codingChoices', which keeps a brain the machine no longer
  // has as what this task NAMES (codingPicker's own test below), and writes the brain or the card - never the role.
  assert.match(picker, /const code = codingChoices\(/);
  assert.match(picker, /const c = codingChoice\(e\.target\.value\); onBrain\?\.\(c\.brain\); onPick\?\.\(c\.pick\);/);
  assert.doesNotMatch(picker, /<em/);
});

test("the hook carries what each worker is for", () => {
  const ui = read("ui.jsx");
  assert.match(ui, /kinds: Object\.fromEntries\(\(data\.data \|\| \[\]\)\.map\(\(a\) => \[a\.Name, a\.Kind\]\)\)/);
  // the hook may carry MORE than these - it grew a "brains" member with the brain-layer
  // work - but "kinds" has to stay on it, which is what this guard is actually for
  assert.match(ui, /const AGENTS_UNREAD = \{ agents: \[\], models: \{\}, cmds: \{\}, kinds: \{\}/);
});

test("the new-task dialog asks the question it means, and passes the kinds", () => {
  // the Board's New is New's one box (TQ-1397): nothing to pick there; the task page keeps its picker for a run started from a task
  const board = read("BoardView.jsx");
  assert.match(board, /<NewSheet open=\{newOpen\} onClose=\{\(\) => setNewOpen\(false\)\}\s/);
  assert.doesNotMatch(board, /Which CLI works it — and which model that CLI runs/);
  assert.match(read("TaskPage.jsx"), /<AgentPicker agents=\{agents\} models=\{models\} kinds=\{kinds\} coding/);
  assert.doesNotMatch(read("NewSheet.jsx"), /<AgentPicker/);
});

test("a general worker is chosen by name alone - the brain is its own picker", () => {
  const ui = read("ui.jsx");
  const picker = ui.slice(ui.indexOf("export const AgentPicker"), ui.indexOf("export const timeAgo"));
  // a role no longer carries a brain (the 2026-09-16 spec), so "researcher · claude" named a CLI the run would not use
  // (the owner, 2026-10-15: "Profile has nothing to do with what brain it uses??")
  assert.doesNotMatch(picker, /models\[a\]\?\.cmd/);
  // ...and a hand-off names no profile at all: the agent is Taskuary, the profile rides behind it (the owner, 2026-10-29)
  assert.match(picker, /\{!coding && !handOff && <Select size="small" value=\{selected/);
  assert.doesNotMatch(picker, /its profile · /);
});

test("Settings defaults and backups offer coding CLIs rather than profile names", () => {
  const settings = read("SettingsView.jsx");
  const defaults = read("AiDefaults.jsx");
  assert.match(settings, /\["coding", "cli"\]\.includes\(String\(a\.Kind \|\| ""\)\.toLowerCase\(\)\)/);
  assert.match(settings, /label: models\[a\.Name\]\?\.cli \|\| models\[a\.Name\]\?\.cmd \|\| a\.Name/);
  assert.match(settings, /automatic — any other coding CLI/);
  // the judge picks a thing that decides rather than a thing that speaks, so it gets its own word
  assert.ok(defaults.includes('{isJudge ? "what decides" : "which AI"}'));      // one word for it on every card (2026-11-11)
  assert.match(defaults, /state\.agent_options \|\| agents/);
});

test("the model box is a dropdown that LOOKS like one: an arrow, and the list opens on click (2026-10-01)", () => {
  const src = readFileSync(fileURLToPath(new URL("../src/AiDefaults.jsx", import.meta.url)), "utf8");
  assert.match(src, /<Autocomplete freeSolo forcePopupIcon openOnFocus /);
});

// A repository dialog asks WHICH CLI, not which worker.
//
// Both shipped coding workers carry rules_doc "coder", so `coder` and `codex` are one job on two
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
  // writes is the brain, never the role, because every coding task's role is `coder`.
  // ...and a brain the machine no longer has is still what this task NAMES: the list used to fall
  // back to brains[0], so filtering to installed brains would have shown a CLI nobody chose.
  assert.match(picker, /const list = coding \? \(brain && !brains\.includes\(brain\) \? \[brain, \.\.\.brains\] : brains\) : roles;/);
  assert.match(picker, /const value = coding \? brain : agent;/);
  assert.match(picker, /onChange=\{\(e\) => \(coding \? onBrain : onAgent\)\(e\.target\.value\)\}/);
  assert.doesNotMatch(picker, /<em/);
});

test("the hook carries what each worker is for", () => {
  const ui = read("ui.jsx");
  assert.match(ui, /setKinds\(Object\.fromEntries\(\(data\.data \|\| \[\]\)\.map\(\(a\) => \[a\.Name, a\.Kind\]\)\)\)/);
  // the hook may carry MORE than these - it grew a "brains" member with the brain-layer
  // work - but "kinds" has to stay on it, which is what this guard is actually for
  assert.match(ui, /return \{ agents, models, cmds, kinds[^}]*\};/);
});

test("the new-task dialog asks the question it means, and passes the kinds", () => {
  const board = read("BoardView.jsx");
  assert.match(board, /Which CLI works it — and which model that CLI runs/);
  assert.doesNotMatch(board, /Agent and model — which CLI works it/);
  assert.match(board, /<AgentPicker agents=\{agents\} models=\{models\} kinds=\{kinds\} coding/);
  assert.match(board, /const \{ agents, models, cmds, kinds[^}]*\} = useAgents\(\)/);
  for (const name of ["NewSheet.jsx", "TasksView.jsx"]) {
    const src = read(name);
    assert.match(src, /<AgentPicker agents=\{agents\} models=\{models\} kinds=\{kinds\} coding/);
  }
  const sheet = read("NewSheet.jsx");
  assert.match(sheet, /onAgent=\{\(a\) => \{ setAgent\(a\); setModel\(""\); \}\}/);
});

test("every other picker is untouched - a general worker is still chosen by name", () => {
  const ui = read("ui.jsx");
  const picker = ui.slice(ui.indexOf("export const AgentPicker"), ui.indexOf("export const timeAgo"));
  // without `coding` the list is every worker, labelled name · cli exactly as before
  assert.match(picker, /\(models\[a\]\?\.cmd \? ` · \$\{models\[a\]\.cmd\}` : ""\)/);
});

test("Settings defaults and backups offer coding CLIs rather than profile names", () => {
  const settings = read("SettingsView.jsx");
  const defaults = read("AiDefaults.jsx");
  assert.match(settings, /\["coding", "cli"\]\.includes\(String\(a\.Kind \|\| ""\)\.toLowerCase\(\)\)/);
  assert.match(settings, /label: models\[a\.Name\]\?\.cli \|\| models\[a\.Name\]\?\.cmd \|\| a\.Name/);
  assert.match(settings, /automatic — any other coding CLI/);
  // the judge picks a thing that decides rather than a thing that speaks, so it gets its own word
  assert.match(defaults, /\{isAgent \? "which CLI" : isJudge \? "what decides" : "which brain"\}/);
  assert.match(defaults, /state\.agent_options \|\| agents/);
});

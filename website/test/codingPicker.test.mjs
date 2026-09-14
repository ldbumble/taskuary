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
  assert.match(picker, /coding = false, kinds = \{\}/);
  assert.match(picker, /coding && Object\.keys\(kinds\)\.length\s*\?\s*agents\.filter\(\(a\) => kinds\[a\] === "coding"\)/);
  assert.match(picker, /const cliOf = \(a\) => models\[a\]\?\.cli \|\| models\[a\]\?\.cmd \|\| a/);
  assert.match(picker, /\{coding \? cliOf\(a\) : a\}/);
});

test("the hook carries what each worker is for", () => {
  const ui = read("ui.jsx");
  assert.match(ui, /setKinds\(Object\.fromEntries\(\(data\.data \|\| \[\]\)\.map\(\(a\) => \[a\.Name, a\.Kind\]\)\)\)/);
  assert.match(ui, /return \{ agents, models, cmds, kinds \};/);
});

test("the new-task dialog asks the question it means, and passes the kinds", () => {
  const board = read("BoardView.jsx");
  assert.match(board, /Which CLI works it — and which model that CLI runs/);
  assert.doesNotMatch(board, /Agent and model — which CLI works it/);
  assert.match(board, /<AgentPicker agents=\{agents\} models=\{models\} kinds=\{kinds\} coding/);
  assert.match(board, /const \{ agents, models, cmds, kinds \} = useAgents\(\)/);
});

test("every other picker is untouched - a general worker is still chosen by name", () => {
  const ui = read("ui.jsx");
  const picker = ui.slice(ui.indexOf("export const AgentPicker"), ui.indexOf("export const timeAgo"));
  // without `coding` the list is every worker, labelled name · cli exactly as before
  assert.match(picker, /\(models\[a\]\?\.cmd \? ` · \$\{models\[a\]\.cmd\}` : ""\)/);
});

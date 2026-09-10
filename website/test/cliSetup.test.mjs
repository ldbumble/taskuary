// Setting a coding CLI up from inside Taskuary: the button is drawn only where there is a road,
// what opens is the CLI running its own onboarding, and the pane is the session the Board shows.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { canSetup, setupTitle } from "../src/cliSetup.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the button is drawn only for an installed CLI Taskuary knows how to set up", () => {
  assert.equal(canSetup({ installed: true, setup: "claude" }), true);
  assert.equal(canSetup({ installed: false, setup: "claude" }), false);   // install it first
  assert.equal(canSetup({ installed: true, setup: "" }), false);          // aider: an API key, no walk
  assert.equal(canSetup(null), false);
});

test("the title says what will happen, and names the CLI", () => {
  assert.match(setupTitle({ label: "Claude Code", setup: "claude" }), /Claude Code/);
});

test("the hook posts the recipe and renders the session it gets back", () => {
  const src = read("cliSetup.jsx");
  assert.match(src, /api\.post\("\/api\/cli\/setup", \{ name \}\)/);
  assert.match(src, /SessionPane/);
  // the pane is a task on the Board: a second press must reattach, never open a second one
  assert.match(src, /existing/);
});

test("nothing is typed into the CLI for the owner", () => {
  // the whole correction: the CLI runs its own onboarding - settings, then the sign-in - and
  // driving one slice of that from outside is guessing at a conversation it has properly
  const src = read("cliSetup.jsx");
  assert.doesNotMatch(src, /\/login/);
  assert.doesNotMatch(read("../../taskuary/clisetup.py"), /\.seed\(/);   // nor server-side
});

test("installing a CLI opens its setup instead of testing a CLI that has never been run", () => {
  const src = read("SetupWizard.jsx");
  assert.match(src, /canSetup\(/);
  assert.match(src, /<CliPane/);
  assert.match(src, /useCliSetup\(\)/);
});

test("a passing test moves the wizard on, and leaves Done to the owner", () => {
  const src = read("SetupWizard.jsx");
  assert.match(src, /api\.post\(`\/api\/agents\/\$\{encodeURIComponent\(cli\.name\)\}\/test`/);
  // nothing closes the pane or the task from here - a pane must not vanish mid-setup
  assert.doesNotMatch(src, /\/wrap/);
});

test("the agents page offers it on a row Taskuary can set up", () => {
  const src = read("AgentsPanel.jsx");
  assert.match(src, /SetupButton/);
  assert.match(src, /useCliSetup\(\)/);
});

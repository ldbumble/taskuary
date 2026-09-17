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

// The three tests that used to live here ("installing a CLI opens its setup instead of testing a
// CLI that has never been run", "the test after a sign-in saves the absolute path, not the bare
// name", "a passing test moves the wizard on, and leaves Done to the owner") checked CliPicker's
// install/sign-in/test sequence *inside SetupWizard.jsx*. The onboarding-walk rewrite deleted that
// duplicate from the panel on purpose (Task 8: "point instead of pretend") - the AI CLI agents
// page (AgentsPanel.jsx) is the only place that sequence runs now, and "the agents page offers it
// on a row Taskuary can set up" below already covers it.

test("the theme note rides with the pane, and Claude Code's own /theme stays claude-only", () => {
  // ThemeHint was exported and rendered NOWHERE from 2026-08-18 (the Terminal tab that carried it
  // was removed) until this: the setup pane is where a theme is actually being chosen.
  assert.match(read("cliSetup.jsx"), /<ThemeHint cli=\{pane\.name\}/);
  const term = read("TerminalView.jsx");
  assert.match(term, /export const ThemeHint = \(\{ cli = "" \}\)/);
  assert.match(term, /cli === "claude"/);      // codex paints with the terminal; it has no /theme
});

test("the agents page offers it on a row Taskuary can set up", () => {
  const src = read("AgentsPanel.jsx");
  assert.match(src, /SetupButton/);
  assert.match(src, /useCliSetup\(\)/);
});

test("the sign-in pane has no closer - a pane must not vanish mid-OAuth", () => {
  const src = read("AgentsPanel.jsx");
  // The INSTALL pane deliberately has a "Close terminal" button that calls /wrap. The SIGN-IN pane
  // deliberately does not: the owner may be mid-browser-round-trip, and Done is theirs on the task.
  // This asymmetry was guarded inside SetupWizard.jsx until the panel stopped carrying a CLI picker.
  const at = src.indexOf("{pane &&");
  assert.notEqual(at, -1);                     // the marker must actually have matched something
  const signin = src.slice(at);
  assert.doesNotMatch(signin, /\/wrap/);
  assert.match(signin, /<CliPane pane=\{pane\}/);
});

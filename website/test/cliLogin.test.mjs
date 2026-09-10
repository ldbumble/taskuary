// Sign in to a coding CLI from inside Taskuary: the button is drawn only where there is a road,
// and the pane it opens is the same session the Board shows.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { canSignIn, signInTitle } from "../src/cliLogin.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the button is drawn only for an installed CLI that has a login recipe", () => {
  assert.equal(canSignIn({ installed: true, login: "claude" }), true);
  assert.equal(canSignIn({ installed: false, login: "claude" }), false);   // install it first
  assert.equal(canSignIn({ installed: true, login: "" }), false);          // aider: an API key, no sign-in
  assert.equal(canSignIn(null), false);
});

test("the title says what will happen, and names the CLI", () => {
  assert.match(signInTitle({ label: "Claude Code", login: "claude" }), /Claude Code/);
});

test("the hook posts the recipe and renders the session it gets back", () => {
  const src = read("cliLogin.jsx");
  assert.match(src, /api\.post\("\/api\/cli\/login", \{ name \}\)/);
  assert.match(src, /SessionPane/);
  // the pane is a task on the Board: a second press must reattach, never open a second flow
  assert.match(src, /existing/);
});

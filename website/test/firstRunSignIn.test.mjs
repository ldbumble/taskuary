// Clicking ChatGPT left every other card on the screen, so it looked like nothing happened; the sign-in was a raw terminal under
// the cards with the pane's theme notes beside it (the owner, 2026-10-15: "you act something happens, show whats next step clearly.
// any error lead them to fix"). The picked card stands alone with its one next step, and the check runs by itself.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { focusOf } from "../src/firstRunFocus.js";

const fr = readFileSync(new URL("../src/FirstRun.jsx", import.meta.url), "utf8");

test("the card being checked, or the one whose fix is open, stands alone - unless the owner asked to see them all", () => {
  const st = { step: "ai", fix: { name: "codex", fix: "signin" } };
  assert.equal(focusOf(st, "", false), "cli-codex");
  assert.equal(focusOf({ step: "ai" }, "claude", false), "cli-claude");
  assert.equal(focusOf(st, "", true), null);
  assert.equal(focusOf({ step: "email", fix: st.fix }, "", false), null);
  assert.equal(focusOf({ step: "ai" }, "", false), null);
});

test("the sign-in runs the CLI's login, hides the pane's theme notes, and checks by itself when it ends", () => {
  assert.match(fr, /openSetup\(\{ \.\.\.cli, login: true \}\)/);
  assert.match(fr, /<CliPane pane=\{pane\}[^>]*hint=\{false\}[^>]*onExit=\{ended\}/);
  assert.match(fr, /Pick a different AI/);
  assert.doesNotMatch(fr, /I've signed in - check again/);
});

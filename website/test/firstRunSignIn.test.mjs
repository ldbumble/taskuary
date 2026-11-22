// Clicking ChatGPT left every other card on the screen, so it looked like nothing happened; the sign-in was a raw terminal under
// the cards with the pane's theme notes beside it (the owner, 2026-10-15: "you act something happens, show whats next step clearly.
// any error lead them to fix"). The picked card stands alone with its one next step, and the check runs by itself.
import test from "node:test";
import assert from "node:assert/strict";

import { focusOf, signinUrl } from "../src/firstRunFocus.js";


test("the card being checked, or the one whose fix is open, stands alone - unless the owner asked to see them all", () => {
  const st = { step: "ai", fix: { name: "codex", fix: "signin" } };
  assert.equal(focusOf(st, "", false), "cli-codex");
  assert.equal(focusOf({ step: "ai" }, "claude", false), "cli-claude");
  assert.equal(focusOf(st, "", true), null);
  assert.equal(focusOf({ step: "email", fix: st.fix }, "", false), null);
  assert.equal(focusOf({ step: "ai" }, "", false), null);
  // ChatGPT signs in in the browser: its card stands alone while it does, and a plan that failed its test is found by its key
  assert.equal(focusOf({ step: "ai" }, "", false, "c7"), "c7");
  assert.equal(focusOf({ step: "ai", fix: { key: "c7", name: "chatgpt", fix: "retry" } }, "", false), "c7");
});


test("the sign-in link is read whole off the login's screen, wrapped rows joined; no link is ''", () => {
  const cols = 20;
  const lines = ["Starting local login", "If your browser did", "https://auth.openai", ".com/oauth/authorize", "?state=xyz", "", "On a remote machine"];
  assert.equal(signinUrl({ cols, lines }), "https://auth.openai.com/oauth/authorize?state=xyz");
  assert.equal(signinUrl({ cols, lines: ["nothing here"] }), "");
  assert.equal(signinUrl(null), "");
});

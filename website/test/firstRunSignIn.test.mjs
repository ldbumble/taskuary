// Clicking ChatGPT left every other card on the screen, so it looked like nothing happened; the sign-in was a raw terminal under
// the cards with the pane's theme notes beside it (the owner, 2026-10-15: "you act something happens, show whats next step clearly.
// any error lead them to fix"). The picked card stands alone with its one next step, and the check runs by itself.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { focusOf, signinUrl } from "../src/firstRunFocus.js";

const fr = readFileSync(new URL("../src/FirstRun.jsx", import.meta.url), "utf8");

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

test("the sign-in runs the CLI's login, hides the pane's theme notes, and checks by itself when it ends", () => {
  assert.match(fr, /openSetup\(\{ \.\.\.cli, login: true \}\)/);
  assert.match(fr, /<CliPane pane=\{pane\}[^>]*hint=\{false\}[^>]*onExit=\{ended\}/);
  assert.match(fr, /Pick a different AI/);
  assert.doesNotMatch(fr, /I've signed in - check again/);
});

test("the sign-in link is read whole off the login's screen, wrapped rows joined; no link is ''", () => {
  const cols = 20;
  const lines = ["Starting local login", "If your browser did", "https://auth.openai", ".com/oauth/authorize", "?state=xyz", "", "On a remote machine"];
  assert.equal(signinUrl({ cols, lines }), "https://auth.openai.com/oauth/authorize?state=xyz");
  assert.equal(signinUrl({ cols, lines: ["nothing here"] }), "");
  assert.equal(signinUrl(null), "");
});

test("the step is a plain sign-in, the terminal only behind Show details", () => {
  assert.match(fr, /Open the sign-in page/);
  assert.match(fr, /Show details/);
  assert.match(fr, /A sign-in page opened in your browser/);
});

test("ChatGPT is a browser sign-in on its own card, then tested and made the AI - no terminal", () => {
  assert.match(fr, /chatgpt\/signin/); assert.match(fr, /chatgpt\/poll/);
  assert.match(fr, /\/api\/setup\/first-run\/connector/);
  assert.match(fr, /Finish signing in to ChatGPT in your browser/);
});

test("past the AI step it can be changed: Back reaches it, the line names the AI, and a working new one moves on", () => {
  // the owner, 2026-10-15: "do you not have the option to go back and change the ai method. meaning no back button?"
  assert.match(fr, /Your AI is \$\{st\.brain\?\.name \|\| "set"\} - it sorts your mail and runs the Assistant\. Pick another here to switch\./);
  assert.match(fr, /back: \{ label: "Back"/); assert.match(fr, /next: \{ label: "Next"/);
  assert.match(fr, /if \(view === "ai" && newAi\) go\("mail"\)/);
  assert.match(fr, /const q = view \|\| frontierOf\(st\);/);
});

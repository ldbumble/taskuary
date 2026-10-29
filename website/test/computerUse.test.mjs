// COMPUTER USE, AS THE OWNER MEETS IT (the computer-use walk, 2026-10-25): a browser step reads as what it did whichever AI ran it, the
// brain menu says which AI can use the browser and be held, and the pane says when it starts, closes, or is being signed in. The JSX
// never loads under node --test, so the components are pinned by their source; the arithmetic and the words by their functions.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { browserStep, describeCall } from "../src/agentSteps.js";
import { viewportFor } from "../src/browserSplit.js";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8").replace(/\r\n/g, "\n");

test("a Codex or Gemini browser step reads as what it did, not 'Ran agent-browser click'", () => {
  const say = (command) => describeCall("shell", { command }).summary;
  assert.equal(say("agent-browser open https://billing.vendor.example/invoices"), "Opened billing.vendor.example");
  assert.equal(say("agent-browser snapshot -i -c"), "Looked at the page");
  assert.equal(say("agent-browser click '@e2'"), "Clicked on the page");
  assert.equal(say('agent-browser find role button "Pay now" click'), "Clicked 'Pay now'");
  assert.equal(say('agent-browser find label "Email" fill "alex@northwind.example"'), "Typed into 'Email'");
  assert.equal(say('agent-browser fill @e1 "Northwind"'), "Typed into a box");
  assert.equal(say("agent-browser --session tq-1 back"), "Went back a page");
  assert.equal(browserStep(["frobnicate"]).summary, "Used the browser (frobnicate)");
});

test("Claude's own description of a browser step still wins over the verb", () => {
  const s = describeCall("Bash", { command: "agent-browser click '@e12'", description: "Press the pay button for invoice INV-1001" });
  assert.equal(s.summary, "Press the pay button for invoice INV-1001");
  assert.equal(s.kind, "page");
});

test("a laptop's pane draws the page at a readable scale", () => {
  assert.equal(viewportFor(538, 347).w, 980);       // 1366x768: was 1200, the page at ~45%
  assert.equal(viewportFor(900, 600).w, 1200);      // a desktop pane keeps the desktop width
});

test("the brain menu says which AI can use the browser and be held, and names one CLI one way", () => {
  const ui = src("ui.jsx");
  assert.match(ui, /export const brainNote = \(b, browser\)/);
  assert.match(ui, /"can't use the browser"/); assert.match(ui, /"browser acts not held"/); assert.match(ui, /"not signed in"/);
  assert.match(ui, /\{b\.label\}\{brainNote\(b, browser\)\}/);
  assert.match(ui, /browser \? "an AI that can use the browser" : "the brain it runs on"/);
  assert.match(src("TaskPage.jsx"), /browser=\{String\(t\?\.Tags \|\| ""\)\.split\(\/\[\\s,\]\+\/\)\.includes\(BROWSER_TAG\)\}/);
});

test("the pane says it is starting, closed, or being signed in - and never scrolls the card under a click", () => {
  const pane = src("BrowserPane.jsx"), term = src("TerminalView.jsx");
  assert.match(pane, /starting the browser…/);
  assert.match(pane, /Taskuary is signing in\$\{hostOf\(url\) \? ` to \$\{hostOf\(url\)\}` : ""\} — the picture resumes in a moment/);
  assert.match(pane, /\{driving && !filling && !turn && \(/);
  assert.equal((pane.match(/focus\(\{ preventScroll: true \}\)/g) || []).length, 2);
  assert.doesNotMatch(pane, /\.focus\(\)/);
  assert.match(term, /The browser closed\$\{lastPage\.current \? ` \(last on/);
  assert.match(term, /It reopens when the agent next needs it\./);
  assert.match(term, /yourTurn \? "browser · your turn - open it"/);
  assert.equal((term.match(/filling=\{!!browser\.filling\}/g) || []).length, 3);
});

test("a held act waits on the live canvas, and the sign-in ask never invites the password", () => {
  const gw = src("GeneralWorkspace.jsx");
  // ...on the browser view when it is on screen (BrowserPane's Approve / Dismiss, 2026-10-28), else its card in the chat
  assert.match(gw, /acts=\{actsHere\}/);
  assert.match(gw, /const actsHere = viewShown \? \(data\?\.browserActs \|\| \[\]\)\.filter\(\(r\) => !heldOn\(r, session\?\.sid\)\) : data\?\.browserActs \|\| \[\];/);
  assert.match(gw, /data-tq-browser-acts=""/);
  assert.match(gw, /acts\.map\(\(r\) => <ReviewDecision key=\{r\.ReviewId\} review=\{r\} onChanged=\{onDraftDecided\} \/>\)/);
  assert.match(gw, /placeholder=\{site \? "Message the agent - never your password" : "Type your answer"\}/);
  assert.match(gw, /Sign in here opens a page Taskuary types from - the agent never sees it\. /);
  assert.match(gw, /Or sign in yourself in the browser, then press Signed in\./);
});

test("saved sign-ins say so when there are none, and the setup key is asked for in plain words", () => {
  const ss = src("SavedSignins.jsx");
  assert.match(ss, /No saved sign-ins\. When an agent asks you to sign in, tick Save to vault/);
  assert.doesNotMatch(ss, /otpauth:\/\//);
});

// The system-setup walkthrough is reachable from the Assistant header, after onboarding as well as during
// first run (PW-189), and it is the AI-led conversation the chat already runs - not a wizard route and not a
// keyword dispatch. The browser harness runs in demo mode where mutating requests are denied, so the entry is
// proven here on the source and by tests/test_setup_skill.py on the prompt it produces.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const view = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
const head = view.slice(view.indexOf('<div className="tq-chat-head">'), view.indexOf('<Popover open={!!aiEl}'));

test("the Assistant header carries the setup entry and it calls the chat's own setup()", () => {
  const at = head.indexOf("Set up Taskuary");
  assert.notEqual(at, -1, "a Set up Taskuary control on the header");
  const button = head.slice(head.lastIndexOf("<button", at), at);
  assert.ok(button.includes("onClick={setup}"), "the header entry runs the same setup() the chat uses");
});

test("setup() opens the conversation in place - no wizard route, no phrase to interpret", () => {
  const fn = view.slice(view.indexOf("const setup = ()"), view.indexOf("const setup = ()") + 900);
  assert.match(fn, /setMsgs\(\(m\) => \[\.\.\.m,/, "the existing conversation is kept, not replaced");
  assert.doesNotMatch(fn, /navigate\(|location\.hash|SetupWizard/, "it does not leave for a wizard");
  assert.doesNotMatch(head, /onClick=\{\(\) => send\("[^"]*set ?up/i, "the entry is not a typed phrase");
});

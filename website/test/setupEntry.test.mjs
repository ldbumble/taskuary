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

// the owner, 2026-10-19: setup is the Setup button at the top - never a choice in the chat, its header or its welcome block
test("the setup entry is the top bar's Setup, not the chat's header or its welcome block", () => {
  assert.equal(head.includes("Set up Taskuary"), false, "the header carries no setup chip");
  assert.equal(view.includes(">Set up Taskuary</button>"), false, "nor does the welcome block");
  const top = fs.readFileSync(path.join(process.cwd(), "src", "TaskHubPage.jsx"), "utf8");
  assert.match(top, /const openSetup = \(\) => \{ go\("Assistant"\); setTimeout\(\(\) => window\.dispatchEvent\(new Event\("tq-first-run"\)\), 60\); \};/);
});

test("setup() opens the conversation in place - no wizard route, no phrase to interpret", () => {
  // setup() now awaits /api/setup/walk (task 10 - the scripted walk), so it is declared async.
  const fn = view.slice(view.indexOf("const setup = "), view.indexOf("const setup = ") + 900);
  assert.match(fn, /setMsgs\(\(m\) => \[\.\.\.m,/, "the existing conversation is kept, not replaced");
  assert.doesNotMatch(fn, /navigate\(|location\.hash|SetupWizard/, "it does not leave for a wizard");
  assert.doesNotMatch(head, /onClick=\{\(\) => send\("[^"]*set ?up/i, "the entry is not a typed phrase");
});

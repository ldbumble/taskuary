// AN UNTRUSTED SENDER'S TASK IS WORKED BY NO AGENT (the owner, 2026-11-11): the chat shows what came in, one plain line why nothing works on
// it, and one Trust action that starts the agent - read off the server's one list (conversation.items `hold`, origin.hold), never worked
// out by the page, and with no "Run anyway" beside it.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the hold is the list's: its line and its one Trust action, drawn in the chat", () => {
  const gw = src("GeneralWorkspace.jsx");
  assert.match(gw, /hold=\{conv\.list\?\.hold \|\| null\}/);
  assert.match(gw, /\{hold && <HeldStart taskId=\{task\.TaskId\} hold=\{hold\} onChanged=\{onTrusted\} \/>\}/);
  assert.doesNotMatch(src("TaskPage.jsx"), /heldStart|HeldStart/, "the page works out no hold of its own");
});

test("one action: Trust, by the label the server words for the sender - no Run anyway", () => {
  const card = src("HeldStart.jsx").replace(/^\/\/.*$/gm, "");
  assert.match(card, /api\.post\(`\/api\/tasks\/\$\{taskId\}\/trust`\)/);
  assert.match(card, /\{busy \? "Starting…" : hold\.person \|\| "Trust them"\}/);
  assert.equal((card.match(/<Button/g) || []).length, 1);
  assert.doesNotMatch(card, /Run anyway|\/release/);
});

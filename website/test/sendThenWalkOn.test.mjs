// CLOSE OUT / APPROVE & SEND WAITS, THEN WALKS ON (the owner, 2026-10-02): unlike Mark done it is not put down at the press -
// the send has to come back clean first, so an error shows on the card. A send that closed the task then moves the walk on;
// one that left it open (a playbook still undecided) stays on it. Plus the same day's removals on the walk.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const path = (f) => fileURLToPath(new URL(`../src/${f}`, import.meta.url));
const read = (f) => readFileSync(path(f), "utf8");

test("a clean send hands over to the task page, which walks on only when the task closed", () => {
  const dec = read("ReviewDecision.jsx"), page = read("TaskPage.jsx");
  assert.match(dec, /onMarkDone = null, onSent = null, onRemind = null, toRow = false/);
  // after the error checks, never instead of them: a refused or failed send keeps the card and says why
  assert.match(dec, /else if \(data\.send_error\) setSendErr\(replySendFailure\(data\)\);\n\s+\/\/[^\n]*\n\s+\/\/[^\n]*\n\s+else if \(data\.ok && verb === "approve" && onSent\) \{ await onSent\(\); setBusy\(false\); return; \}/);
  assert.match(dec, /else if \(data\.ok && verb !== "reject" && onSent\) \{ await onSent\(\);/);   // the close-out (merge + reply) too
  assert.match(page, /onMarkDone=\{askFinish\} onSent=\{sent\} onRemind=/);
  const sent = page.slice(page.indexOf("const sent = async"), page.indexOf("// Remind me: put away"));
  assert.match(sent, /api\.get\(`\/api\/tasks\/\$\{selected\}`\)/);
  assert.match(sent, /if \(done\) \{ onLeave\?\.\(\); return closedHere\(\); \}/);
  assert.match(sent, /loadDetail\(selected\)/);   // still open: stay on it, read again
});

test("an fyi batch offers its own All read, next and no second Next", () => {
  assert.match(read("AssistantView.jsx"), /kind === "proposal" \|\| kind === "fyis" \|\| !\(actions\.items/);
});

test("the meeting card promises no prep it cannot do", () => {
  const cards = read("assistantCards.jsx");
  const meeting = cards.slice(cards.indexOf("export function MeetingCard"), cards.indexOf("export function ReportCard"));
  assert.doesNotMatch(meeting, /Getting prepped|calendar\/prep|promote=/);
});

test("the cards the task view replaced are gone", () => {
  const cards = read("assistantCards.jsx"), view = read("AssistantView.jsx");
  for (const c of ["AgentCard", "AgentDoneCard", "TaskCard", "WrapupCard"]) {
    assert.doesNotMatch(cards, new RegExp(`export function ${c}\b`));
    assert.doesNotMatch(view, new RegExp(`\b${c}\b`));
  }
  assert.equal(existsSync(path("agentCardView.js")), false);
});

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
  assert.match(dec, /onMarkDone = null, onSent = null, onRemind = null, closeOnSend = false, toRow = false/);
  // after the error checks, never instead of them: a refused or failed send keeps the card and says why
  assert.match(dec, /else if \(data\.send_error\) setSendErr\(replySendFailure\(data\)\);(\n\s+\/\/[^\n]*)+\n\s+else if \(data\.ok && \(verb === "approve" \|\| \(verb === "close_unsent" && r\.Kind !== "slot"\)\) && onSent\) \{\n\s+setSent\(verb === "approve"\); setBusy\(false\); await onSent\(\{ closes: closesIt && verb === "approve" && \(data\.reply \? !!data\.reply\.ok : true\) \}\); return;/);
  // ...and a chat's Mark done (close_unsent: it copies the draft and closes) walks on the same way - it stood as "task · done" (2026-10-20)
  assert.match(dec, /else if \(data\.ok && verb !== "reject" && onSent\) \{ setSent\(true\); setBusy\(false\); await onSent\(\{ closes: closesIt && !!data\.reply\?\.ok \}\);/);   // the close-out (merge + reply) too
  assert.match(page, /onMarkDone=\{askFinish\} onSent=\{sent\} closeOnSend onRemind=/);
  const sent = page.slice(page.indexOf("const sent = async"), page.indexOf("// Remind me: put away"));
  assert.match(sent, /api\.get\(`\/api\/tasks\/\$\{selected\}`\)/);
  assert.match(sent, /if \(done\) \{ onLeave\?\.\(\); return closedHere\(\); \}/);
  assert.match(sent, /loadDetail\(selected\)/);   // still open: stay on it, read again
});

// THE REPLY THAT WENT CLOSES THE TASK (the owner, 2026-10-29): on the task page's Close out only, only after the server's receipt
test("a reply sent from Close out closes the task once the send succeeded; a failed one leaves it open", () => {
  const dec = read("ReviewDecision.jsx"), page = read("TaskPage.jsx");
  assert.match(dec, /const closesIt = closeOnSend && onTask && !!onSent;/);   // a slot, a proposal, a clarification close nothing
  // the close rides on onSent, which runs only past the error checks: a send_error sets the error and returns before it
  const decide = dec.slice(dec.indexOf("const decide = async"), dec.indexOf("const release = async"));
  assert.ok(decide.indexOf("setSendErr(replySendFailure(data))") < decide.indexOf("await onSent({ closes"));
  assert.doesNotMatch(decide.slice(0, decide.indexOf("await api.post")), /onSent|complete/, "nothing closes at the press");
  const sent = page.slice(page.indexOf("const sent = async"), page.indexOf("// Remind me: put away"));
  // ...through the server's one gate, which keeps it open while anything on it still waits on the owner (a held `git push`, 2026-10-29):
  // the page walks on only when that gate says it closed
  assert.match(sent, /const sent = async \(\{ closes = false \} = \{\}\) => \{\n\s+if \(closes\) \{/);
  assert.match(sent, /out = await closeAfterSend\(api, selected\);[^\n]*\n\s+if \(out\?\.closed\) \{ onLeave\?\.\(\); return closedHere\(\); \}/);
  assert.doesNotMatch(sent, /finish\("done"\)/, "never Mark done's close, which has no gate");
  assert.match(read("closeAgent.jsx"), /export const closeAfterSend = \(api, tid\) => runOperation\(api, "task\.complete", tid, \{ after_send: true \}\);/);
  assert.match(dec, /stays = closesIt \? "then the task closes"/);
});

test("an fyi batch offers its own All read, next and no second Next", () => {
  assert.match(read("AssistantView.jsx"), /m\.proposal \|\| kind === "proposal" \|\| kind === "fyis"\s*\? said : idle \? IDLE_CHIPS/);
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

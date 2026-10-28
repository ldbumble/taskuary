import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// A REPLY THAT CANNOT LEAVE FROM HERE (the owner, 2026-10-22: "there should be no mark done under reply if you can't send out
// message ... mark done is on the tasks. also no send out results on something you can't send out")
const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("an unsendable draft has no close of its own under it - the task's Mark done closes", () => {
  const rd = read("ReviewDecision.jsx");
  assert.doesNotMatch(rd, /copyClose/, "no copy-and-close under the draft or on the row");
  assert.doesNotMatch(rd, /Copy the draft and answer it there yourself/, "no line saying what to do - the button does");
});

// THE OWNER, 2026-10-22: "a Copy button beside Redraft" that copies and does NOT close; the reason it cannot send is its hover
test("an unsendable draft has Copy beside Redraft: it copies, closes nothing, and its badge says it went", () => {
  const rd = read("ReviewDecision.jsx");
  const copy = rd.slice(rd.indexOf("const copyIt = async"), rd.indexOf("const copyIt = async") + 400);
  assert.match(copy, /navigator\.clipboard\.writeText\(value\); setCopied\(true\);/);
  assert.doesNotMatch(copy, /decide\(|onMarkDone|close_unsent|task\.complete/, "a copy closes nothing");
  assert.match(rd, /\) : !canSendIt \? \(\s*\/\*[\s\S]*?\*\/\s*<Button size="small" variant=\{lit === no\("copy"\) \? "contained" : "outlined"\}[^>]*onClick=\{copyIt\}\s*title=\{copyTitle\}/);
  assert.match(rd, /\{copied \? `✓ \$\{btn\("copy", "done"\)\}` : btn\("copy"\)\}<\/Button>/);
  // ...registered as the card's own verb, so the Advisor finds it under the draft; the bar never draws it
  assert.match(rd, /\{ id: no\("copy"\), label: copied \? `✓ \$\{btn\("copy", "done"\)\}` : btn\("copy"\), tone: "s", disabled: busy \|\| !value\.trim\(\), run: copyIt, title: copyTitle,/);
  // ...and Redraft still stands beside it
  assert.match(rd, /\{canRedraft && !r\.Stale && !delivery\.frozen && (!warnTop && )?<Button/);   // a warned Redraft sits over the draft (2026-10-28)
});

test("a draft decided already - answered in the chat itself - is not a delivery failure", () => {
  assert.match(read("ReviewDecision.jsx"), /if \(data\.already\) \{ onChanged\?\.\(\); setBusy\(false\); return; \}/);
});

test("Email a summary (Share's, once Send out results) is not offered where nothing can be sent - and is no row button of its own", () => {
  const page = read("TaskPage.jsx");
  assert.match(page, /const cantSend = pendingReview \? !draftCanSend\(caps, pendingReview\) : !!replyMessage && !canSend\(caps, replyMessage\.Channel\);/);
  assert.match(page, /canSummary = !liveSession && !cantSend && notDone/);
  assert.match(page, /summary: canSummary \? \(\) => setEmailOpen\(true\) : null/);
  assert.doesNotMatch(page, /\{ id: "email"/);
});

test("TaskPage reads the capabilities through its own hook - `caps` there was GoalSteps', and the page threw", () => {
  const page = read("TaskPage.jsx"), body = page.slice(page.indexOf("export default function TaskPage("));
  assert.match(body, /const caps = useCapabilities\(\), canCode = caps\.coding;/);
});

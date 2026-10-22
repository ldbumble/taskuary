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
  assert.match(rd, /\) : !canSendIt \? null : r\.Stale \? \(/);
  assert.match(rd, /Copy the draft and answer it there yourself - \$\{btn\("close"\)\} on the task closes it\./);
});

test("a draft decided already - answered in the chat itself - is not a delivery failure", () => {
  assert.match(read("ReviewDecision.jsx"), /if \(data\.already\) \{ onChanged\?\.\(\); setBusy\(false\); return; \}/);
});

test("Send out results is not offered where nothing can be sent", () => {
  const page = read("TaskPage.jsx");
  assert.match(page, /const cantSend = pendingReview \? !draftCanSend\(caps, pendingReview\) : !!replyMessage && !canSend\(caps, replyMessage\.Channel\);/);
  assert.match(page, /\.\.\.\(!liveSession && !cantSend \? \[\{ id: "email"/);
});

test("TaskPage reads the capabilities through its own hook - `caps` there was GoalSteps', and the page threw", () => {
  const page = read("TaskPage.jsx"), body = page.slice(page.indexOf("export default function TaskPage("));
  assert.match(body, /const caps = useCapabilities\(\), canCode = caps\.coding;/);
});

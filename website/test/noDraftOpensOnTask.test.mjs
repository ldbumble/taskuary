// AN EMPTY CLOSE OUT IS NOT WHERE THE TASK IS UP TO (the owner, 2026-11-02): a chat asked the owner to email somebody, the task's
// checklist owed that email ("Email Paula Vance - the 2:30 meeting · to draft") and nothing was drafted yet - the page opened on Close out
// with no draft in it. "It should show the task, not close out, as there is no close-out draft created." An email owed and not drafted
// is a line on Close out's list, never something of its own; a drafted one waiting for Send is.
import test from "node:test";
import assert from "node:assert/strict";
import { closeHolds, focusOf, sectionHere, workPane } from "../src/taskLayout.js";
import { stageOf } from "../src/stages.js";
import { taskSource } from "./taskSource.mjs";

const owed = { text: "Email Paula Vance - the 2:30 meeting", out: { kind: "email", to: "paula@vendor.example" }, done: false, rid: null };
// where a reply task with a sender opens, given what Close out holds - TaskPage's own chain (focusOf -> stageOf -> sectionHere)
const opensOn = (holds) => {
  const pane = workPane({ stage: "reply", kind: "reply", hasSender: true, replyHas: holds.has });
  return sectionHere({ stage: stageOf({ focus: focusOf({ pane, owed: holds.waits }), drafted: holds.has }) });
};

test("an email the checklist owes with nothing drafted opens the task on Came from, not an empty Close out", () => {
  const h = closeHolds({ checklist: [owed], reviews: [] });
  assert.deepEqual(h, { has: false, waits: false });
  assert.equal(opensOn(h), "from");
});

test("a drafted email waiting for Send, a reply draft or something that went still open Close out", () => {
  const rv = { ReviewId: 7, Kind: "slot", Status: "pending" }, drafted = { checklist: [{ ...owed, rid: 7 }], reviews: [rv] };
  assert.deepEqual(closeHolds(drafted), { has: true, waits: true });
  assert.equal(opensOn(closeHolds(drafted)), "close");
  assert.equal(opensOn(closeHolds({ checklist: [owed], pending: true })), "close");
  assert.equal(opensOn(closeHolds({ proposals: 1 })), "close");
  assert.deepEqual(closeHolds({ sent: true }), { has: true, waits: false });
  for (const k of ["ended", "closed", "writeup"]) assert.equal(closeHolds({ [k]: true }).has, true, k);
  assert.equal(closeHolds({ outside: 1 }).has, true);
});

test("the page reads what Close out holds from closeHolds, never from the checklist's owed lines", () => {
  const src = taskSource();
  assert.match(src, /const \{ has: replyHas, waits: sendWaits \} = closeHolds\(\{/);
  assert.doesNotMatch(src, /replyHas = [^;]*owesEmails/);
});

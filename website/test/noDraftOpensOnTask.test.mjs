// AN EMAIL OWED AND NOT DRAFTED IS NOT A SEND WAITING (the owner, 2026-11-02): a chat asked the owner to email somebody, the task's checklist
// owed that email ("Email Paula Vance - the 2:30 meeting · to draft") and nothing was drafted yet - the page opened as if a Send waited.
// "It should show the task ... as there is no draft created." An email owed and not drafted is a line on the list; a drafted one waiting
// for Send is the move. Read for a plain to-do, the one kind whose page opens where its stage says (every other kind opens on its chat).
import test from "node:test";
import assert from "node:assert/strict";
import { focusOf, homeSection, replyHolds, workPane } from "../src/taskLayout.js";
import { stageOf } from "../src/stages.js";
import { taskSource } from "./taskSource.mjs";

const owed = { text: "Email Paula Vance - the 2:30 meeting", out: { kind: "email", to: "paula@vendor.example" }, done: false, rid: null };
// where a to-do with a sender opens, given what waits on a Send - TaskPage's own chain (focusOf -> stageOf -> homeSection)
const opensOn = (holds) => {
  const pane = workPane({ stage: "reply", kind: "task", hasSender: true, replyHas: holds.has });
  return homeSection("task", stageOf({ focus: focusOf({ pane, owed: holds.waits }), drafted: holds.has }));
};

test("an email the checklist owes with nothing drafted opens the to-do on Came from", () => {
  const h = replyHolds({ checklist: [owed], reviews: [] });
  assert.deepEqual(h, { has: false, waits: false });
  assert.equal(opensOn(h), "from");
});

test("a drafted email waiting for Send, a reply draft or something that went open the chat", () => {
  const rv = { ReviewId: 7, Kind: "slot", Status: "pending" }, drafted = { checklist: [{ ...owed, rid: 7 }], reviews: [rv] };
  assert.deepEqual(replyHolds(drafted), { has: true, waits: true });
  assert.equal(opensOn(replyHolds(drafted)), "agent");
  assert.equal(opensOn(replyHolds({ checklist: [owed], pending: true })), "agent");
  assert.equal(opensOn(replyHolds({ proposals: 1 })), "agent");
  assert.deepEqual(replyHolds({ sent: true }), { has: true, waits: false });
  for (const k of ["ended", "closed", "writeup"]) assert.equal(replyHolds({ [k]: true }).has, true, k);
  assert.equal(replyHolds({ outside: 1 }).has, true);
  // ...and every other kind opens on its chat, whatever waits
  assert.equal(homeSection("reply", "to_reply"), "agent");
  assert.equal(homeSection("coding", "to_start"), "agent");
});

test("the page reads what waits on a Send from replyHolds, never from the checklist's owed lines", () => {
  const src = taskSource();
  assert.match(src, /const \{ has: replyHas, waits: sendWaits \} = replyHolds\(\{/);
  assert.doesNotMatch(src, /replyHas = [^;]*owesEmails/);
});

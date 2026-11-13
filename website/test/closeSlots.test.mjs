// A task says what closes it (spec 2026-10-05): its emails are slot reviews, shown in their own block - never the reply card.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pendingReplyReview, sentReplyReview, slotReviews, unsentReplyReview } from "../src/taskLifecycle.js";

const slot = { ReviewId: 9, Kind: "slot", Status: "pending", DraftText: "Tab 1 is fine." };
const reply = { ReviewId: 3, Kind: "draft_reply", Status: "pending", DraftText: "Thanks, done." };

test("a slot draft is never the task's reply", () => {
  assert.equal(pendingReplyReview([slot]), undefined);
  assert.equal(pendingReplyReview([slot, reply]), reply);
  assert.equal(sentReplyReview([{ ...slot, Status: "approved" }]), undefined);
  assert.equal(unsentReplyReview([{ ...slot, Status: "rejected" }]), undefined);
});

test("the slot block gets every slot review", () => {
  assert.deepEqual(slotReviews([reply, slot, { ...slot, ReviewId: 10 }]).map((r) => r.ReviewId), [9, 10]);
});

test("an email card says nothing of the app's own workings, and one that went stays as its sent card", () => {
  // the owner, 2026-11-13: "Closes when sent · 0 of 1" and "waits for your yes · added by the agent" over the card are internal - and
  // pressing Send on one email closed the box: "never close actions boxes. once sent just say sent"
  const src = readFileSync(new URL("../src/SlotList.jsx", import.meta.url), "utf8");
  for (const w of ["Closes when sent", "waits for your yes", "added by the agent"]) assert.ok(!src.includes(w), w);
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(page, /r\.Kind !== "slot" && \["approved", "edited", "sent"\]/, "a sent email is drawn as its SentCard, as a reply is");
});

test("Approve all never sweeps up an email the agent added, or one with no address", async () => {
  const { bulkSendable } = await import("../src/taskLifecycle.js");
  const items = [{ rid: 9, out: { to: "a@x.example" } }, { rid: 10, out: { to: "b@x.example", by: "agent" } }, { rid: 11, out: { to: "Gail" } }];
  const reviews = [slot, { ...slot, ReviewId: 10 }, { ...slot, ReviewId: 11 }];
  assert.deepEqual(bulkSendable(items, reviews).map((r) => r.ReviewId), [9]);
});

test("the footer says what closes the task", async () => {
  const { completionLine } = await import("../src/taskLifecycle.js");
  assert.match(completionLine(true, false), /so does Send - Send and close or Mark done closes it/);   // Send never closes (2026-10-18); Send and close does (2026-11-03)
  assert.match(completionLine(false, false), /Send leaves the task open - Send and close or Mark done closes it/);
  assert.match(completionLine(true, true), /so does sending its emails - Mark done closes it/);   // the last email closes nothing (slots._left)
  assert.match(completionLine(false, false), /Automatic task/);
  assert.match(completionLine(true, false, true), /press Mark done/);       // nobody to answer: no reply to send
});

// ONE PROMISE (the UI audit, 2026-10-21): the header said "closes itself when the work is done", Close out "Sending it never closes
// the task", Send out results "the task closes once it is sent" - on one reply task. No send closes a task; only an agent's own done
// on a task that owes nobody an answer does.
test("every line about closing makes the one promise the code keeps", async () => {
  const { completionFact, completionLine } = await import("../src/taskLifecycle.js");
  for (const [manual, emails, noSender] of [[true, false, false], [true, true, false], [false, false, false], [false, true, true], [true, false, true]]) {
    assert.equal(completionFact(manual, emails, noSender), "stays open until you Mark done");
    assert.match(completionLine(manual, emails, noSender), /Mark done/);
    assert.doesNotMatch(completionLine(manual, emails, noSender), /closes when its emails|close it and prepare the reply/);
  }
  assert.equal(completionFact(false, false, true), "closes itself when its agent is done");   // an agent's job with nobody behind it
  const results = readFileSync(new URL("../src/EmailSomeone.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(results, /closes once it is sent/);
  assert.match(results, /Sending it leaves the task open until you Mark done\./);
});

test("waiting emails open Close out, and it says how many", async () => {
  const { focusStage, waitingEmails } = await import("../src/taskLifecycle.js");
  const checklist = [{ id: "a", out: { to: "p@x.example" }, rid: 9 }, { id: "b", out: { to: "Gail" } }];
  assert.equal(waitingEmails(checklist, [slot]), 1);
  assert.equal(focusStage({ kind: "coding", task: "waiting", agent: "stopped and saved", emails: 1 }), "reply");
  assert.equal(focusStage({ kind: "coding", task: "waiting", agent: "agent waiting on you", emails: 1 }), "agent");
});

// THE OWNER, 2026-11-10: "it created reply with nothing in it" - a recipient nobody has written to is no card: never drawn in the chat
test("a recipient with no draft is not drawn, and a task with only such ones draws no emails block", () => {
  const list = readFileSync(new URL("../src/SlotList.jsx", import.meta.url), "utf8");
  assert.match(list, /filter\(\(i\) => i\.out && !i\.done && byRid\[i\.rid\]\?\.Status === "pending"\)/);
  assert.doesNotMatch(list, />Drop<\/Button>/);
  assert.match(readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8"), /const owesEmails = emailsWaiting > 0;/);
});

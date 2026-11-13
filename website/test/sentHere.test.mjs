import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { sentLine, sentSaid, sentStands, sentTitle } from "../src/sentLine.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// SEND AND CLOSE SAYS SO (the owner, 2026-11-05: "nothing happens besides the box disappears")
test("a reply that went says where, and that the task is closing or why it stays", () => {
  assert.equal(sentLine({ channel: "whatsapp", closing: true }), "Sent on WhatsApp - closing the task");
  assert.equal(sentLine({ channel: "email", closing: true }), "Sent by email - closing the task");
  assert.equal(sentLine({ channel: "teams", closing: false, kept: "an agent is still working" }), "Sent on Teams. The task stays open: an agent is still working");
  assert.equal(sentLine({ channel: "", to: "Ray Colton", closing: false }), "Sent to Ray Colton");
  const page = read("TaskPage.jsx");
  assert.match(page, /const chatCards = sentBox \? <SentCard \{\.\.\.sentBox\} \/> :/);
  assert.match(read("ReviewDecision.jsx"), /said: verb === "approve" \? \{ text: value, channel: r\.Channel \|\| "", to: replyContext\(r\), subject: deliverySubject\(r\), id: r\.ReviewId \} : null/);
});

// the owner, 2026-11-09: "leave the card in the turn with the pressed button" - the sent block said it with no card around it
test("a sent reply stays its card: the subject, the words, and ✓ Sent on the button it took with where it went beside it", () => {
  assert.equal(sentTitle({ subject: "Re: Q3 numbers", to: "Erin Blake" }), "Re: Q3 numbers");
  assert.equal(sentTitle({ subject: "Portal login", to: "erin@northwind.example" }), "Portal login");     // a new email is no reply
  assert.equal(sentTitle({ subject: "RE: Q3 numbers" }), "RE: Q3 numbers");
  assert.equal(sentTitle({ to: "Erin Blake" }), "Reply to Erin Blake");
  assert.equal(sentSaid({ channel: "email", closing: true }), "by email - closing the task");
  assert.equal(sentSaid({ to: "Ray Colton" }), "to Ray Colton");
  const card = read("SentCard.jsx");
  assert.match(card, /<PressedButton pressed="sent" label="✓ Sent" \/>/);      // ...a mark, never a button nobody can press (passedCard.test.mjs)
});

// THE LIVE SHAPE (the audit, 2026-11-13, on the real CLI): Send pressed, he stays on the task, the sender writes again, the agent drafts the
// new reply. The sent letter stood where the new draft belonged - "✓ Sent" under the turn that said "it waits for your Send", no Send to press
test("the sent card holds its draft's place only until the task reads it as gone - then it is its turn's card, and what waits now is drawn", () => {
  const here = { id: 2, text: "Yes, March 12 works.", channel: "email", closing: false };
  const pressed = [{ ReviewId: 2, Status: "pending" }], read = [{ ReviewId: 2, Status: "approved" }], again = [...read, { ReviewId: 3, Status: "pending" }];
  assert.equal(sentStands(here, pressed, true), here, "at the press, before the task is read again: where its draft stood");
  assert.equal(sentStands(here, read, true), null, "read as gone: its turn's card says it");
  assert.equal(sentStands(here, again, true), null, "and the next draft is never hidden behind it");
  assert.equal(sentStands({ ...here, id: 2 }, [{ ReviewId: 2, Status: "edited" }], true), null);
  assert.equal(sentStands(here, read, false), here, "a task with no turns has no such card: it stays where it stood");
  assert.equal(sentStands(null, again, true), null);
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /const sentBox = sentStands\(sentHere, allReviews, inTurns\);/);
  assert.match(page, /WENT\.includes\(r\.Status\) && r\.ReviewId !== sentBox\?\.id\)/);      // ...its turn's card is drawn from the same word
});

// THE LIVE SHAPE (the audit, 2026-11-13, on the real CLI): a reply had gone, the agent wrote two emails and came to rest; under their cards the
// line read "The task stays open while its agent is still working." beside the chip "agent waiting on you". A chat agent keeps its session
// after it answers: alive is not at work
test("the line under what was sent says the agent is still working only while a turn is at work", async () => {
  const { generalAnswered, stillWorking } = await import("../src/taskLifecycle.js");
  const atRest = { alive: true, busy: false, waiting: true }, atWork = { alive: true, busy: true };
  assert.equal(stillWorking(true, generalAnswered(true, atRest)), false, "answered and waiting on him: not working");
  assert.equal(stillWorking(true, generalAnswered(true, atWork)), true);
  assert.equal(stillWorking(true, generalAnswered(false, { alive: true })), true, "a coding session has no such word: live is at work, as before");
  assert.equal(stillWorking(false, false), false);
  assert.match(readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8"), /stillWorking\(liveSession, answered\) \? "The task stays open while its agent is still working\."/);
});


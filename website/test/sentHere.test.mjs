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
  assert.match(read("ReviewDecision.jsx"), /said: verb === "approve" \? \{ text: value, channel: r\.Channel \|\| "", to: sentTo\(r\), subject: deliverySubject\(r\), id: r\.ReviewId, done: pw\.sentAs \} : null/);
});

// the owner, 2026-11-09: "leave the card in the turn with the pressed button" - the sent block said it with no card around it
test("a sent reply stays its card: the subject, the words, and ✓ Sent on the button it took with where it went beside it", async () => {
  assert.equal(sentTitle({ subject: "Re: Q3 numbers", to: "Erin Blake" }), "Re: Q3 numbers");
  assert.equal(sentTitle({ subject: "Portal login", to: "erin@northwind.example" }), "Portal login");     // a new email is no reply
  assert.equal(sentTitle({ subject: "RE: Q3 numbers" }), "RE: Q3 numbers");
  assert.equal(sentTitle({ to: "Erin Blake" }), "Reply to Erin Blake");
  assert.equal(sentSaid({ channel: "email", closing: true }), "by email - closing the task");
  assert.equal(sentSaid({ to: "Ray Colton" }), "to Ray Colton");
  // ...IN THE DEMO A SEND IS PLAYED (the owner, 2026-11-15): the card settles and says what did not happen - one sentence, the server's own
  assert.equal(sentLine({ channel: "email", demo: true }), "Sent - in the demo, nothing left this computer");
  assert.equal(sentSaid({ channel: "email", demo: true }), "in the demo, nothing left this computer");
  const { markDemo } = await import("../src/demoWorld.js");
  markDemo(true); assert.equal(sentLine({ channel: "teams" }), "Sent - in the demo, nothing left this computer"); markDemo(false);
  assert.equal(sentLine({ channel: "teams" }), "Sent on Teams");
  const card = read("SentCard.jsx");
  assert.match(card, /<PressedButton pressed="sent" label=\{sentMark\(p\)\} \/>/);      // ...a mark, never a button nobody can press (passedCard.test.mjs)
});

// THE LIVE SHAPE (the audit, 2026-11-13, on the real CLI): Send pressed, he stays on the task, the sender writes again, the agent drafts the
// new reply. The sent letter stood where the new draft belonged - "✓ Sent" under the turn that said "it waits for your Send", no Send to press
test("in a chat with turns the pressed card is the only one that says it went - from the press, never a second copy under the chat", () => {
  const here = { id: 2, text: "Yes, March 12 works.", channel: "email", closing: false };
  assert.equal(sentStands(here, true), null, "at the press, before the task is read again: the pressed card in its turn says it - never a second one");
  assert.equal(sentStands(here, false), here, "a task with no turns has no such card: it stays where it stood");
  assert.equal(sentStands(null, true), null);
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /const sentBox = sentStands\(sentHere, inTurns\);/);
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


// A PRESS SAYS WHAT IT DOES, FROM THE PRESS TO THE CLOSE (the owner, 2026-11-16: "Accept and close" on an invite showed nothing for 15 seconds - the
// calendar was slow - and then the task was gone; its card had said "Sending…", "Checking delivery…" and "Sent by email" over an invite)
// THE LIVE SHAPE (the walk, 2026-11-17): he pressed Send on one of the task's emails. The card read "You pressed Send - sending…", then its Send
// and Don't send lit again (the answer had come, the re-read had not), then it was gone (the re-read had it sent, the chat's list did not yet),
// then a Sent card stood at the turn's cards at another width. One node per email, in its turn, from its draft to its Sent: what it looks like
// comes from where its press stands, kept by the review and not by the card, so a card drawn again mid-send never resets to a lit Send
test("an email's card goes sending… then Sent in its one place, and a card drawn again keeps where its press stands", async () => {
  const { cardLook, markOf, pressMark } = await import("../src/sentLine.js");
  const r = { ReviewId: 41, Kind: "slot", Status: "pending" };
  assert.equal(cardLook(r), "live");
  pressMark(41, { state: "going", pressed: "approve" });
  assert.equal(cardLook(r), "going", "mounted again mid-send: sending…, never a lit Send");
  assert.equal(markOf(41).pressed, "approve");
  pressMark(41, { state: "sent" });
  assert.equal(cardLook(r), "sent", "answered: Sent, whatever a read a beat behind still says");
  assert.equal(cardLook({ ...r, DeliveryState: "sending" }), "sent", "and never the frozen form again");
  pressMark(41, null);
  assert.equal(cardLook({ ...r, Status: "sent" }), "sent", "read as gone: Sent from the review alone");
  assert.equal(cardLook({ ...r, Status: "edited" }), "sent");
  assert.equal(cardLook(r), "live", "a send that did not go is the live card again");
  const rd = read("ReviewDecision.jsx"), page = read("TaskPage.jsx"), gw = read("GeneralWorkspace.jsx");
  assert.doesNotMatch(rd, /const \[sent, setSent\] = useState/, "the press is the review's, not the card's");
  assert.doesNotMatch(rd, /if \(delivery\.frozen\) setSent\(false\);/);
  assert.match(rd, /if \(look === "sent" && !proposal && !co\) return <SentCard /, "Sent is the card's own last look");
  assert.match(rd, /else if \(data\.ok && verb === "approve" && !proposal\) setSent\(true\);/, "an email's Send with no page behind it is Sent from its answer");
  // ...one node per email, keyed by its review, drawn by the chat in its turn - pending and sent alike; the block under the chat holds none
  assert.match(page, /key: `rv:\$\{r\.ReviewId\}`[^\n]*letter: true/);
  assert.doesNotMatch(page, /r\.Kind !== "action" && WENT\.includes/, "no second sent card for an email");
  assert.match(page, /\{!inTurns && <SlotList /);
});

// WALK 9, 2026-11-23: an act's Approve read "running…", then Approve and Dismiss lit again for 2-7 s, then "✓ Approved" - its press answered
// and the card stood unpressed until the re-read came. A press that landed stays pressed until the review reads decided: one state, press to result
test("an act's Approve that landed stays pressed until the review reads it decided - never Approve again in between", async () => {
  const { cardLook, endPress, pressMark } = await import("../src/sentLine.js");
  const r = { ReviewId: 77, Kind: "proposal", Status: "pending" };
  pressMark(77, { state: "going", pressed: "approve" });
  pressMark(77, { state: "landed", pressed: "approve" });      // ...its decide answered ok
  endPress(77);                                                 // ...and the press's own busy ends
  assert.equal(cardLook(r), "going", "pressed, still - never the lit Approve");
  assert.equal(cardLook({ ...r, Status: "approved" }), "sent", "the re-read: decided, from the review alone");
  pressMark(78, { state: "going", pressed: "approve" }); endPress(78);
  assert.equal(cardLook({ ReviewId: 78, Status: "pending" }), "live", "a press that did not land is the live card again");
  pressMark(77, null);
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { sentLine, sentSaid, sentTitle } from "../src/sentLine.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// SEND AND CLOSE SAYS SO (the owner, 2026-11-05: "nothing happens besides the box disappears")
test("a reply that went says where, and that the task is closing or why it stays", () => {
  assert.equal(sentLine({ channel: "whatsapp", closing: true }), "Sent on WhatsApp - closing the task");
  assert.equal(sentLine({ channel: "email", closing: true }), "Sent by email - closing the task");
  assert.equal(sentLine({ channel: "teams", closing: false, kept: "an agent is still working" }), "Sent on Teams. The task stays open: an agent is still working");
  assert.equal(sentLine({ channel: "", to: "Ray Colton", closing: false }), "Sent to Ray Colton");
  const page = read("TaskPage.jsx");
  assert.match(page, /const chatCards = sentHere \? <SentCard \{\.\.\.sentHere\} \/> :/);
  assert.match(read("ReviewDecision.jsx"), /said: verb === "approve" \? \{ text: value, channel: r\.Channel \|\| "", to: replyContext\(r\), subject: deliverySubject\(r\), id: r\.ReviewId \} : null/);
});

// the owner, 2026-11-09: "leave the card in the turn with the pressed button" - the sent block said it with no card around it
test("a sent reply stays its card: the subject, the words, and ✓ Sent on the button it took with where it went beside it", () => {
  assert.equal(sentTitle({ subject: "Q3 numbers", to: "Erin Blake" }), "Re: Q3 numbers");
  assert.equal(sentTitle({ subject: "RE: Q3 numbers" }), "RE: Q3 numbers");
  assert.equal(sentTitle({ to: "Erin Blake" }), "Reply to Erin Blake");
  assert.equal(sentSaid({ channel: "email", closing: true }), "by email - closing the task");
  assert.equal(sentSaid({ to: "Ray Colton" }), "to Ray Colton");
  const card = read("SentCard.jsx");
  assert.match(card, /data-tq-pressed="sent"[\s\S]*✓ Sent<\/Button>/);
});

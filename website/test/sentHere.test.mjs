import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { sentLine } from "../src/sentLine.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// SEND AND CLOSE SAYS SO (the owner, 2026-11-05: "nothing happens besides the box disappears")
test("a reply that went says where, and that the task is closing or why it stays", () => {
  assert.equal(sentLine({ channel: "whatsapp", closing: true }), "Sent on WhatsApp - closing the task");
  assert.equal(sentLine({ channel: "email", closing: true }), "Sent by email - closing the task");
  assert.equal(sentLine({ channel: "teams", closing: false, kept: "an agent is still working" }), "Sent on Teams. The task stays open: an agent is still working");
  assert.equal(sentLine({ channel: "", to: "Ray Colton", closing: false }), "Sent to Ray Colton");
  const page = read("TaskPage.jsx");
  assert.match(page, /const chatCards = sentHere && cardsIn \? <SentHere \{\.\.\.sentHere\} \/> :/);
  assert.match(read("ReviewDecision.jsx"), /said: verb === "approve" \? \{ text: value, channel: r\.Channel \|\| "", to: replyContext\(r\), id: r\.ReviewId \} : null/);
});

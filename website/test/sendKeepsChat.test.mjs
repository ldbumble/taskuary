import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stageOf, mainView, sectionOf } from "../src/stages.js";

// SEND KEEPS THE PAGE WHERE IT IS (the owner, 2026-10-27: "I hit send ... it reopened the task page"). On a real mailbox the sent copy comes
// back marked as Taskuary's own (ReviewSent), so sentElsewhere drops it; with the draft gone nothing waited on a Send, the stage read "a reply
// owed, nothing written" and its main view was the task. The reply that went still counts - and it went from the chat, which stays the page.
const src = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");

test("a reply sent from here keeps the stage drafted, and the page on the chat", () => {
  assert.match(src, /replyHolds\(\{ pending: !!pendingReview, sent: !!sentReview,/, "the sent reply counts");
  const drafted = stageOf({ focus: "reply", drafted: true }), owed = stageOf({ focus: "reply", drafted: false });
  assert.equal(mainView({ stage: drafted }), "work", "with the sent reply counted, the chat is the page");
  assert.notEqual(mainView({ stage: owed }), "work", "...which is what the page flipped to without it");
  // ...a drafted or sent reply is the chat's; one owed with nothing written opens a plain to-do on Came from (every other kind opens on its chat)
  assert.equal(sectionOf(drafted), "agent");
  assert.equal(sectionOf(owed), "from");
});

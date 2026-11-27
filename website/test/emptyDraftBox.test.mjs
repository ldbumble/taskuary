// AN EMPTY DRAFT IS SAID, AND A NEW DRAFT UNDER AN OPEN CARD IS SHOWN (2026-11-04): Close out showed a blank box under a grey Send, and
// the Assistant's rewrite landed on the review while the open card kept the emptied box it had.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { editAfterRefile } from "../src/replyDraft.js";
import { draftState, EMPTY_LINE, replyCardShown } from "../src/sendState.js";

test("a draft filed under an open card replaces the edit made on the one before it", () => {
  assert.equal(editAfterRefile({ text: "", held: null, keep: false }), null);                 // the emptied box shows the rewrite
  assert.equal(editAfterRefile({ text: "Mine", keep: true }), "Mine");           // beside a refreshed draft, or held for him: the owner's stays
  assert.equal(editAfterRefile({ text: "  ", keep: true }), null);               // ...a box he emptied holds no words: the new draft shows
  assert.equal(editAfterRefile({ text: "Thanks Gail", keep: false }), null);     // his own ask for other words took his back
});


test("an empty draft reads as one, never as a blank box", () => {
  const agent = { Kind: "draft_reply", DraftText: "", DraftBy: "agent:assistant" };
  assert.deepEqual([draftState(agent).state, draftState(agent).line], ["empty", EMPTY_LINE]);
  assert.equal(EMPTY_LINE, "The draft came back empty - Redraft, or tell me what to say.");
  assert.equal(draftState({ DraftText: " ", DraftError: "the draft came back empty" }).state, "empty");
  // ...and a rewrite that came back empty over a draft that stands says the box holds the one before it
  const kept = draftState({ DraftText: "Friday at ten works.", DraftError: "the draft came back empty" });
  assert.equal(kept.state, "kept");
  assert.match(kept.line, /didn't come back - it was empty\. The draft below is the one before it/);
  assert.equal(draftState({ DraftText: "Friday." }).state, "drafted");
  assert.equal(draftState({ DraftText: "" }).state, "undrafted");
  assert.equal(draftState({ DraftText: "", DraftError: "the AI connector timed out" }).state, "failed");
});

// NO REPLY BOX THE AGENT DID NOT WRITE (the owner, 2026-11-27: "Agents don't just draw boxes unless it needs approval to send email? why would it
// draw anything before that"): a reply owed sat empty in the chat with a line of what it needed. Where an agent works the task the card is its
// reply, written - whatever the record of an empty one says
test("an owed reply with no words is no card in an agent's chat, whatever its record says; a written one is", () => {
  assert.equal(replyCardShown({ Kind: "draft", Status: "pending", DraftText: "" }), false);
  assert.equal(replyCardShown({ Kind: "draft", DraftText: "", DraftNeeds: "which March dates suit Gail" }), false);
  assert.equal(replyCardShown({ Kind: "draft", DraftText: "", DraftError: "the AI connector timed out" }), false);
  assert.equal(replyCardShown({ Kind: "draft", DraftText: "", DraftBy: "agent:assistant" }), false);
  assert.equal(replyCardShown({ Kind: "draft", DraftText: "Friday." }), true);
  assert.equal(replyCardShown({ Kind: "draft", DraftText: "Friday.", DraftError: "the draft came back empty" }), true);   // the one before a failed rewrite stands
  assert.equal(replyCardShown(null), false);
  const page = fs.readFileSync(path.join(process.cwd(), "src", "TaskPage.jsx"), "utf8");
  // ...its turn's card in a chat with turns (replyNode), drawn only once written; the chat's own only with no turns (a8fab80d9)
  assert.match(page, /const replyNode = inTurns && pendingReview && replyCardShown\(pendingReview\) \?/);
  assert.match(page, /const chatReview = !inTurns \? pendingReview : null;/);
  assert.match(page, /const chatBody = \(pendingReview = chatReview\) =>/);
  assert.match(page, /const waits = !!\(chatReview \|\|/);
  assert.match(page, /\{replyEmpty && !inTurns && \(/, "the box nothing was said about only on a to-do no agent has touched");
});

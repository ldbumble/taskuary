// AN EMPTY DRAFT IS SAID, AND A NEW DRAFT UNDER AN OPEN CARD IS SHOWN (2026-11-04): Close out showed a blank box under a grey Send, and
// the Assistant's rewrite landed on the review while the open card kept the emptied box it had.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { editAfterRefile } from "../src/replyDraft.js";
import { draftState, EMPTY_LINE } from "../src/sendState.js";

test("a draft filed under an open card replaces the edit made on the one before it", () => {
  assert.equal(editAfterRefile({ text: "", held: null, keep: false }), null);                 // the emptied box shows the rewrite
  assert.equal(editAfterRefile({ text: "Thanks Gail", held: null, keep: false }), null);
  assert.equal(editAfterRefile({ text: "x", held: { text: "Seen, Gail" }, keep: false }), "Seen, Gail");   // the other card's edit on it
  assert.equal(editAfterRefile({ text: "Mine", held: null, keep: true }), "Mine");           // beside a refreshed draft: the owner's stays
});

test("the card follows the filed draft, not only the draft it was drawn with", () => {
  const card = fs.readFileSync(path.join(process.cwd(), "src", "ReviewDecision.jsx"), "utf8");
  assert.match(card, /setTextNow\(editAfterRefile\(\{ text, held: heldOf\(r\), keep \}\)\)/);
  assert.match(card, /\}, \[r\.ReviewId, filed\]\);/);
  assert.match(card, /\["needs", "failed", "empty", "kept"\]\.includes\(draftState\(r\)\.state\)/);
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

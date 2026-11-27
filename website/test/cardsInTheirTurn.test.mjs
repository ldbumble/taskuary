// THE SPINE AUDIT, 2026-11-09: a card did not stay in the turn that raised it, and one waiting act drew two cards. Everything that waited - a
// held step, a browser act, a drafted skill - rode one block under whichever turn was newest; a held act and a skill stood again at the
// chat's foot with a second Approve; and a pressed card was placed by reading an answer's stamp as when its turn BEGAN, which on a general chat
// is when it ended. Each card stands where the chat's log put it (chatlog.advance, tests/test_chatlog.py); the page draws each once, there.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { askNote } from "../src/reviewProposal.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("what the foot's boxes said over a held act and a skill is said over its one card", () => {
  const act = (p) => ({ Kind: "action", Status: "pending", DraftText: JSON.stringify(p) });
  assert.match(askNote(act({ action: "browser_act", what: "Press Renew", url: "https://portal.vendor.example/renew" })), /^The agent's browser waits for your yes\./);
  assert.match(askNote(act({ action: "save_skill", name: "Renewals", text: "# Renewals" })), /^Approve saves this skill to Reports → Skills/);
  assert.equal(askNote(act({ action: "close_task", why: "the folder is clear" })), "", "a card that says itself gets no line over it");
});


// ONE ACTION BOX AT A TIME, A HARD RULE (the owner's live task, 2026-11-19): a held browser step stood at the front reading "1 of 2 · next: the
// reply to Gail Moreno", and the reply's box was drawn under it - the page's reply block (`next`) and the letters were drawn with no look at
// the line. What the line holds behind its front stands nowhere; while the front is another card, no door to write a reply stands beside it.
test("a reply the line holds behind its front draws no box", async () => {
  const ws = read("GeneralWorkspace.jsx");
  // ...a card the line holds has no row in the log (chatlog.advance) and the page places none of its own: nothing to draw
  assert.doesNotMatch(ws, /looseCards|nextLoose|lettersHere/);
  assert.match(read("TaskPage.jsx"), /const chatReview = !inTurns \? pendingReview : null;/);
  // ...and no reply door of the page's own stands beside it: Reply is his ask to the task's agent (the owner, 2026-11-27)
  assert.doesNotMatch(read("TaskPage.jsx"), /replyDoorOpen|data-tq-reply-again|data-tq-draft-ai/);
});

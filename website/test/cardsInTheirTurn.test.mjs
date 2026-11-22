// THE SPINE AUDIT, 2026-11-09: a card did not stay in the turn that raised it, and one waiting act drew two cards. Everything that waited - a
// held step, a browser act, a drafted playbook - rode one block under whichever turn was newest; a held act and a playbook stood again at the
// chat's foot with a second Approve; and a pressed card was placed by reading an answer's stamp as when its turn BEGAN, which on a general chat
// is when it ended. The server names each card's turn now (tests/test_cards_stand_in_their_turn.py); the page draws each once, there.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { placeCards, turnOf } from "../src/agentSummary.js";
import { askNote } from "../src/reviewProposal.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
// a general chat: asked at 09:00 and answered at 09:02, asked again at 11:00 and answered at 11:01 - each answer stamped when its turn ENDED
const chat = [{ id: "comment-1", role: "user", createdAt: "2026-11-05 09:00:00" }, { id: "comment-2", role: "assistant", createdAt: "2026-11-05 09:02:00" },
  { id: "comment-3", role: "user", createdAt: "2026-11-05 11:00:00" }, { id: "comment-4", role: "assistant", createdAt: "2026-11-05 11:01:00" }];
const after = (cards, turns, messages = chat) => placeCards(cards, messages, turns).map((c) => c.after);

test("in a general chat a card stands in the turn the server names, never the one its stamp falls after", () => {
  const cards = [{ key: "held:7", rid: 7, at: "2026-11-05 09:01:00" }, { key: "held:8", rid: 8, at: "2026-11-05 11:00:30", waits: true }];
  assert.deepEqual(cards.map((c) => turnOf(chat, c.at)), ["comment-4", "comment-2"], "read as begin-stamps both stood in the wrong turn");
  assert.deepEqual(after(cards, { 7: "comment-2", 8: "comment-4" }), ["comment-2", "comment-4"]);
  assert.equal(placeCards(cards, chat, { 7: "comment-2", 8: "comment-4" })[1].waits, true, "the card is handed on whole");
});

// ...NEVER AT THE FOOT (the owner, 2026-11-10: "approve should be there then once that's done it shoudl continue after it not above it.. it's
// just a row in the chat"): a card no answer has followed was raised by the turn at work - the newest - and stands in it
test("a card no answer has followed stands in the newest turn, and moves into the turn that answers", () => {
  const card = [{ key: "rv9", rid: 9, at: "2026-11-05 11:05:00", waits: true }], newest = chat.filter((m) => m.role === "assistant").at(-1).id;
  assert.deepEqual(after(card, { 9: null }), [newest]);
  assert.deepEqual(after(card, {}), [newest], "never the foot");
  const answered = [...chat, { id: "comment-6", role: "assistant", createdAt: "2026-11-05 11:06:00" }];
  assert.deepEqual(after(card, { 9: "comment-6" }, answered), ["comment-6"]);
});

test("a coding chat names no turns - its own are stamped as they begin - and an answer the thread does not draw is no place to stand", () => {
  const coding = [{ id: "run-1", role: "assistant", createdAt: "2026-11-05 09:00:00" }, { id: "run-2", role: "assistant", createdAt: "2026-11-05 11:00:00" }];
  assert.deepEqual(after([{ key: "held:7", rid: 7, at: "2026-11-05 09:01:00" }, { key: "held:8", rid: 8, at: "2026-11-05 11:00:30" }], null, coding), ["run-1", "run-2"]);
  assert.deepEqual(after([{ key: "sent:3", rid: 3, at: "2026-11-05 09:01:00" }], { 3: "comment-99" }), ["comment-4"], "as it was placed before");
  assert.deepEqual(after([{ key: "land", at: "2026-11-05 09:01:00" }], { 3: "comment-2" }), ["comment-4"], "a card of no review is placed by its time");
});


test("what the foot's boxes said over a held act and a playbook is said over its one card", () => {
  const act = (p) => ({ Kind: "action", Status: "pending", DraftText: JSON.stringify(p) });
  assert.match(askNote(act({ action: "browser_act", what: "Press Renew", url: "https://portal.vendor.example/renew" })), /^The agent's browser waits for your yes\./);
  assert.match(askNote(act({ action: "amend_playbook", name: "Renewals", text: "# Renewals" })), /^Approve saves this playbook to Reports → Playbooks/);
  assert.equal(askNote(act({ action: "close_task", why: "the folder is clear" })), "", "a card that says itself gets no line over it");
});


// ONE ACTION BOX AT A TIME, A HARD RULE (the owner's live task, 2026-11-19): a held browser step stood at the front reading "1 of 2 · next: the
// reply to Gail Moreno", and the reply's box was drawn under it - the page's reply block (`next`) and the letters were drawn with no look at
// the line. What the line holds behind its front stands nowhere; while the front is another card, no door to write a reply stands beside it.
test("a reply the line holds behind its front draws no box, and no reply door stands beside another card's front", async () => {
  const { replyDoorOpen } = await import("../src/chatStream.js");
  const q = { live: [744], held: [745] };
  assert.equal(replyDoorOpen(q, null), false, "a door to write a reply beside the browser step's front");
  assert.equal(replyDoorOpen({ live: [745], held: [] }, 745), true); assert.equal(replyDoorOpen({ live: [], held: [] }, null), true);
  const ws = read("GeneralWorkspace.jsx");
  // ...a card the line holds has no row in the log (chatlog.advance) and the page places none of its own: nothing to draw
  assert.doesNotMatch(ws, /looseCards|nextLoose|lettersHere/);
  assert.match(read("TaskPage.jsx"), /const chatReview = !inTurns \? pendingReview : null;/);
  assert.match(read("TaskPage.jsx"), /!pendingReview && !inRow && !replyEmpty && replyDoorOpen\(detail\?\.queue, null\) && \(/);
});

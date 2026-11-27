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
// reply to Gail Moreno", and the reply's box was drawn under it. What the line holds behind its front stands nowhere - and NOTHING OF TASKUARY'S
// STANDS UNDER A CARD THAT WAITS (locked rule 10, 2026-11-27): the page's block, a start's why and the queued line wait for the card's press.
test("a reply the line holds behind its front draws no box, and nothing of the page's stands under a card that waits", async () => {
  const { cardWaits } = await import("../src/chatStream.js");
  const turn = (cards) => ({ kind: "turn", id: "t1", cards });
  assert.equal(cardWaits([turn([{ review: 744, status: "pending" }])]), true, "a card in its turn that waits");
  assert.equal(cardWaits([{ kind: "card", id: "c1", review: 744, status: "pending" }]), true, "a card row of its own");
  assert.equal(cardWaits([turn([{ review: 744, status: "approved" }]), { kind: "line", id: "l1" }]), false, "a pressed card holds nothing back");
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /\{!!next && !cardWaits\(items\) && <Box data-tq-next-steps=""/);
  assert.match(ws, /\{!hold && !!idle && !cardWaits\(merged\.items\) && /);
  assert.match(ws, /\{queued && !cardWaits\(merged\.items\) && /);
  // ...a card the line holds has no row in the log (chatlog.advance) and the page places none of its own: nothing to draw
  assert.doesNotMatch(ws, /looseCards|nextLoose|lettersHere/);
  assert.match(read("TaskPage.jsx"), /const chatReview = !inTurns \? pendingReview : null;/);
  assert.doesNotMatch(read("TaskPage.jsx"), /data-tq-handoff-card|A reply is optional|data-tq-reply-again/, "no hand-off form, Draft reply or optional-reply line in the chat");
});

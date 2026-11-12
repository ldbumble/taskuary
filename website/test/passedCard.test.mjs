// A CARD YOU HAVE MOVED PAST IS OLD NEWS (the owner, 2026-11-10: "no once youa re passed it, it should stay where it is with buttons grayed out.
// You can ask the agent to bring it back?"): the server settles it (proposals.move_on); the page keeps it in its turn, one greyed look for
// every kind, and greys a reply draft while the agent's turn re-decides it.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("a passed card is the server's word, drawn once in its turn, greyed, never as a pressed card", () => {
  const card = src("PassedCard.jsx"), page = src("TaskPage.jsx");
  assert.match(card, /export const PASSED_NOTE = "set aside when you moved on";/, "proposals.SET_ASIDE, word for word");
  assert.match(card, /r\?\.Status === "superseded" && r\?\.DecideNote === PASSED_NOTE/);
  assert.match(card, /pressed = passed \? "passed"/); assert.match(card, /data-tq-act-state=\{pressed\}/);
  // ...and one nobody can press draws no button at all (the owner, 2026-11-11: "the question has 2 approve buttons?"): its state in words
  assert.doesNotMatch(card, /data-tq-pressed="passed"|btn\("approve"/); assert.match(card, /\{!passed && <PressedButton pressed=\{pressed\} \/>\}/);
  assert.match(page, /const \{ asks: askCards, past: pressedCards \} = splitHeld\(allReviews\.filter\(\(r\) => !isPassed\(r\)\), \[\.\.\.asks, \.\.\.decidedAsks\]\)/, "never drawn as Dismissed");
  assert.match(page, /const turnCards = \[\.\.\.passedCards, /, "in the turn that raised it");
});

test("a reply draft the owner prompted past is greyed where it stands, for good (draftPassed.test.mjs)", () => {
  assert.doesNotMatch(src("TaskPage.jsx"), /replanning=\{agentState/);
  assert.match(src("ReviewDecision.jsx"), /const off = busy \|\| drafting \|\| passed;/);
});

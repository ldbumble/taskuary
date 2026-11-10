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
  assert.match(card, /data-tq-act-state="passed"/); assert.match(card, /<Button size="small" variant="outlined" disabled data-tq-pressed="passed"/);
  assert.match(page, /const \{ asks: askCards, past: pressedHeld \} = splitHeld\(allReviews\.filter\(\(r\) => !isPassed\(r\)\), asks\)/, "never drawn as Dismissed");
  assert.match(page, /const turnCards = \[\.\.\.passedCards, /, "in the turn that raised it");
});

test("a reply draft is greyed while its agent's turn re-decides it", () => {
  assert.match(src("TaskPage.jsx"), /replanning=\{agentState === AGENT\.working && !!pendingReview\}/);
  assert.match(src("ReviewDecision.jsx"), /const off = busy \|\| drafting \|\| replanning;/);
});

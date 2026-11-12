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

// THE CARD ROUND, 2026-11-12 (every card kind drawn in every state and read): a draft a later turn replaced was the whole reply card drawn again,
// dimmed, under the new one - a greyed Send, and Add CC / Add BCC that looked live; every pressed card wore a greyed <button>; a settled
// held step was titled "... waits for your yes" over "✓ Approved"
test("a replaced draft is its record - its words, greyed, no button - and the reply card knows no passed state", () => {
  const card = src("ReplacedDraft.jsx");
  assert.doesNotMatch(src("TaskPage.jsx"), /replanning=\{agentState/);
  assert.match(card, /className="tq-conv-past" data-tq-replaced=\{r\.ReviewId\} data-tq-past-card="superseded"/);
  assert.doesNotMatch(card, /ReviewDecision|<Button|<button/);
  assert.match(src("ReviewDecision.jsx"), /const off = busy \|\| drafting;/);
  assert.doesNotMatch(src("ReviewDecision.jsx"), /PassedCtx|data-tq-passed-draft/);
});

test("the press a card took is a mark, never a button - one mark for a proposal, held steps, a sent reply and a landing", () => {
  const card = src("PassedCard.jsx");
  assert.match(card, /export const PressedButton = \(\{ pressed, label = "" \}\)[\s\S]*<Box component="span" role="status" data-tq-pressed=\{pressed\}/);
  assert.doesNotMatch(card, /<Button|\bdisabled\b/);
  assert.match(src("SentCard.jsx"), /<PressedButton pressed="sent" label="✓ Sent" \/>/);
  assert.match(src("LandingCard.jsx"), /<PressedButton pressed=\{s\.landed\.how\} label=\{w\.done\} \/>/);
  for (const f of ["SentCard.jsx", "PassedCard.jsx", "ReplacedDraft.jsx"]) assert.doesNotMatch(src(f), /<Button[^>]*\bdisabled\b/, f);
  // ...and a settled card is titled by what it was (its lead), with its result beside it once
  assert.match(card, /title = p\?\.lead \|\| p\?\.title \|\| heldLead\(proposalFrom\(r\) \|\| \{\}\)\.lead/);
  assert.match(card, /\(!same\(done\.what, title\) && done\.what\)/);
  // ...and one review is one card in the chat: an act with its own card is not drawn again under its settled one
  assert.match(src("GeneralWorkspace.jsx"), /\.\.\.\(post && !got\.length && !used\.has\(`post:\$\{c\.review\}`\)/);
});

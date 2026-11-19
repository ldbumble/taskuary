// A CARD YOU HAVE MOVED PAST IS THE CARD IT WAS, ITS BUTTONS GREYED (the owner, 2026-11-18: "don't need reason. just keep it with buttons but the
// buttons grayed out once you moved on"): the server settles it (proposals.move_on); the page keeps it in its turn - its own card, `past`.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("a passed card is the server's word, drawn once in its turn as its own card with `past`, never as a pressed card", () => {
  const card = src("PassedCard.jsx"), page = src("TaskPage.jsx");
  assert.match(card, /export const PASSED_NOTE = "set aside when you moved on";/, "proposals.SET_ASIDE, word for word");
  assert.match(card, /r\?\.Status === "superseded" && \[PASSED_NOTE, "not needed - the agent finished without it"\]\.includes\(r\?\.DecideNote\)/);
  assert.match(page, /node: g\.held \? <HeldSteps reviews=\{g\.reviews\} past \/>\n\s+: r\.Kind === "slot" \? <Letter [^\n]* past \/> : <ReviewDecision review=\{r\} past \/>/);
  // ...the pressed card says only what was pressed: no passed state, no reason
  assert.doesNotMatch(card, /passed \?|PASSED_LINE|r\.Why/);
  assert.match(page, /const \{ asks: askCards, past: pressedCards \} = splitHeld\(allReviews\.filter\(\(r\) => !isPassed\(r\)\), \[\.\.\.asks, \.\.\.decidedAsks\]\)/, "never drawn as Dismissed");
  assert.match(page, /const turnCards = \[\.\.\.replyNode, \.\.\.passedCards, /, "in the turn that raised it");
});

// THE CARD ROUND, 2026-11-12 (every card kind drawn in every state and read): a draft a later turn replaced was the whole reply card drawn again,
// dimmed, under the new one - a greyed Send, and Add CC / Add BCC that looked live; every pressed card wore a greyed <button>; a settled
// held step was titled "... waits for your yes" over "✓ Approved"
test("a replaced draft is the reply card it was, greyed - one road for every card moved past", () => {
  const page = src("TaskPage.jsx");
  assert.doesNotMatch(page, /replanning=\{agentState|ReplacedDraft/);
  assert.match(page, /node: <ReviewDecision review=\{r\} past \/> \}\)\);/);
  assert.match(src("ReviewDecision.jsx"), /const off = busy \|\| drafting;/);
  assert.doesNotMatch(src("ReviewDecision.jsx"), /PassedCtx|data-tq-passed-draft/);
});

test("the press a card took is a mark, never a button - one mark for a proposal, held steps, a sent reply and a landing", () => {
  const card = src("PassedCard.jsx");
  assert.match(card, /export const PressedButton = \(\{ pressed, label = "" \}\)[\s\S]*<Box component="span" role="status" data-tq-pressed=\{pressed\}/);
  assert.doesNotMatch(card, /<Button|\bdisabled=\{/);
  assert.match(src("SentCard.jsx"), /<PressedButton pressed="sent" label=\{sentMark\(p\)\} \/>/);
  assert.match(src("LandingCard.jsx"), /<PressedButton pressed=\{s\.landed\.how\} label=\{w\.done\} \/>/);
  for (const f of ["SentCard.jsx", "PassedCard.jsx"]) assert.doesNotMatch(src(f), /<Button[^>]*\bdisabled\b/, f);
  // ...and a settled card is titled by what it was (its lead), with its result beside it once
  assert.match(card, /title = p\?\.lead \|\| p\?\.title \|\| heldLead\(proposalFrom\(r\) \|\| \{\}\)\.lead/);
  assert.match(card, /\(!same\(done\.what, title\) && done\.what\)/);
  // ...and one review is one card in the chat: an act with its own card is not drawn again under its settled one
  assert.match(src("GeneralWorkspace.jsx"), /\.\.\.\(post && !got\.length && !used\.has\(`post:\$\{c\.review\}`\)/);
});

// ...ONE PROP, ONE LOOK (the owner, 2026-11-18: "just keep it with buttons but the buttons grayed out once you moved on"): a card moved past is
// drawn under MovedPast - every button in it off at once, greyed, out of the Tab order - and a card inside one is greyed once, not twice as faint
test("a card moved past keeps its buttons, every one of them off, greyed once", async () => {
  const { build } = await import("esbuild");
  const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
    import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser"; import { MovedPast } from "./src/PassedCard.jsx";
    const card = (on, inner) => <MovedPast on={on}><button>Send</button>{inner}</MovedPast>;
    export const html = (on, nested) => renderToStaticMarkup(card(on, nested ? card(true) : null));` },
    bundle: true, write: false, format: "esm", jsx: "automatic", platform: "browser", logLevel: "silent", define: { "process.env.NODE_ENV": '"production"' } });
  const { html } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString("base64")}`);
  assert.equal(html(false), "<button>Send</button>", "a live card is untouched");
  assert.match(html(true), /^<fieldset disabled="" inert="" data-tq-moved-past="" aria-disabled="true" style="[^"]*opacity:0\.6;filter:grayscale\(1\)[^"]*"><button>Send<\/button><\/fieldset>$/);
  assert.equal(html(true, true).match(/<fieldset/g).length, 1, "greyed once");
  assert.equal(html(true, true).match(/<button>Send<\/button>/g).length, 2, "its buttons stay");
});

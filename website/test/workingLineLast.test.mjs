// THE WORKING LINE IS THE CHAT'S LAST WORD (the owner, 2026-11-18: "if you generate image thinking should move to under it no?? ... this is a
// chat"): a picture the turn made, a page it published, a question it asked or a card it raised stood UNDER "Comparing PNG conversion
// histograms" while the turn worked - the dots must be the last thing drawn in a turn at work, under whatever it has made so far.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("a turn at work draws its files, pages, question and cards above its working line, never under it", () => {
  const src = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  const turn = src.slice(src.indexOf("const ConvTurn ="), src.indexOf("const RetryCtx"));
  const at = (s) => { const i = turn.indexOf(s); assert.ok(i > 0, `${s} is drawn in the turn`); return i; };
  const dots = at('data-tq-working=""');
  for (const s of ["<PublishedPages", "<TurnFiles", "{ask}", "data-tq-turn-cards"]) assert.ok(at(s) < dots, `${s} stands above the working line`);
});

// ...AND WHAT IT MADE STAYS WHERE IT STOOD WHEN THE ANSWER COMES (the API walk, 2026-11-20): a picture the turn made drew under its steps while
// it worked, and its answer - words that come only at the turn's end - was then drawn above it, so the picture jumped down under his eyes.
// The files and pages a turn made stand between its work and its words, the same place live and finished
test("a turn's files and pages are drawn above its answer, so the answer arriving never moves them", () => {
  const src = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  const turn = src.slice(src.indexOf("const ConvTurn ="), src.indexOf("const RetryCtx"));
  const said = turn.indexOf("<SaidText");
  assert.ok(said > 0);
  for (const s of ["<PublishedPages", "<TurnFiles"]) assert.ok(turn.indexOf(s) > 0 && turn.indexOf(s) < said, `${s} stands above the answer`);
});

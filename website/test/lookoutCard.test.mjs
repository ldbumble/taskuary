// THE LOOKING-OUT-FOR-YOU IDEA ON ITS CARD (lookout.py; the owner, 2026-11-02 evening): the family word in the card's own place, the next
// step and the pitch on lines of their own, and every message or task it rests on a link that opens it in the app - the canvas's link road
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vocab from "../../taskuary/lanes.json" with { type: "json" };
import { ideaWord } from "../src/lanes.js";
import { canvasRequestFromHash } from "../src/canvasLinks.js";

const cards = readFileSync(new URL("../src/assistantCards.jsx", import.meta.url), "utf8");
const idea = cards.slice(cards.indexOf("export const citeHref"), cards.indexOf("export function MessageCard"));

test("each family has its own word, never just 'advisor idea', and sits in the Advisor's ideas", () => {
  const words = { credit: "credit", pitch: "pain → fix", money: "money left on the table", early_warning: "early warning", leverage: "leverage" };
  for (const [k, w] of Object.entries(words)) { assert.equal(ideaWord(k), w); assert.equal(vocab.idea_kinds[k].section, "ideas"); }
  assert.match(idea, /label=\{look \? `Advisor · \$\{ideaWord\(card\.idea_kind\)\}` : "Advisor"\}/, "the table's header names the family");
  assert.match(idea, /kicker=\{<>\{ideaWord\(card\.idea_kind\)\}/, "the card's kicker is the family word");
});

test("the next step and the pitch are two lines, on both the card and the table", () => {
  assert.match(idea, /\["Suggestion", look \? a\.next_step \|\| a\.suggest : a\.suggest\], \["Pitch", look && a\.pitch\]/);
  assert.match(idea, /<Facts rows=\{rows\} \/>/, "the table's Came from draws the same rows");
  assert.match(idea, /facts = rows\.filter/);
});

test("what it rests on opens in the app, on the canvas's link road", () => {
  assert.match(idea, /export const citeHref = \(ref\) => \{ const m = \/\^\(msg\|task\)\(\\d\+\)\$\/\.exec/);
  assert.match(idea, /onClick=\{\(ev\) => \{ ev\.preventDefault\(\); openAppLink\(e\.href\); \}\}/, "in-window, never a new tab");
  assert.doesNotMatch(idea, /target="_blank"/);
  assert.match(idea, /\["Rests on", cites\]/);
  // ...and the links it writes are ones the canvas opens: a mail's card, a task's view
  assert.deepEqual(canvasRequestFromHash("#msg=12"), { kind: "msg", mid: 12, n: 0 });
  assert.deepEqual(canvasRequestFromHash("#task=7"), { kind: "task", tid: 7, n: 0 });
});

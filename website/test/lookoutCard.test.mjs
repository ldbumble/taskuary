// THE LOOKING-OUT-FOR-YOU IDEA (lookout.py; the owner, 2026-11-02 evening): the family word in its own place, the next step and the pitch on
// lines of their own, and every message or task it rests on a link that opens it in the app - the canvas's link road. On the table it is the
// one task page (madeTask.js): what it rests on is its Came from
import test from "node:test";
import assert from "node:assert/strict";
import vocab from "../../taskuary/lanes.json" with { type: "json" };
import { ideaWord } from "../src/lanes.js";
import { canvasRequestFromHash } from "../src/canvasLinks.js";
import { citeHref, ideaSource } from "../src/madeTask.js";

test("each family has its own word, never just 'advisor idea', and sits in the Advisor's ideas", () => {
  const words = { credit: "credit", pitch: "pain → fix", money: "money left on the table", early_warning: "early warning", leverage: "leverage" };
  for (const [k, w] of Object.entries(words)) { assert.equal(ideaWord(k), w); assert.equal(vocab.idea_kinds[k].section, "ideas"); }
});

test("what it rests on opens in the app, on the canvas's link road", () => {
  assert.equal(citeHref("msg12"), "#msg=12"); assert.equal(citeHref("task7"), "#task=7"); assert.equal(citeHref("https://x.example"), null);
  const src = ideaSource({ action: { type: "lookout", evidence: [{ ref: "msg12", label: "the invoice" }, { ref: "task7", label: "the close" }, { ref: "elsewhere" }] } });
  assert.deepEqual(src.links.map((l) => l.href), ["#msg=12", "#task=7"], "only what the app can open");
  // ...and the links it writes are ones the canvas opens: a mail's card, a task's view
  assert.deepEqual(canvasRequestFromHash("#msg=12"), { kind: "msg", mid: 12, n: 0 });
  assert.deepEqual(canvasRequestFromHash("#task=7"), { kind: "task", tid: 7, n: 0 });
});

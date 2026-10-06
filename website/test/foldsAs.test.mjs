// A PROPOSAL MADE WITH NOTHING ON THE TABLE HAS NO KEY, and the canvas folding nothing has no key either: `null === null` folded
// every such proposal as it was drawn, so "confirm below" stood over a title line with no Confirm (2026-10-06).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { foldsAs } from "../src/funnelPile.js";

test("nothing folded folds nothing, a keyless card included", () => {
  for (const [f, k] of [[null, null], [undefined, undefined], [null, undefined], [undefined, null], [null, "msg:3"], ["msg:3", null]]) assert.equal(foldsAs(f, k), false, `${f} / ${k}`);
  assert.equal(foldsAs("msg:3", "msg:3"), true);
  assert.equal(foldsAs("msg:3", "agent:7"), false);
});

test("the conversation reads the fold through foldsAs, never a bare ===", () => {
  const src = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(src, /\.folded\s*(===|!==)\s*\w+(\.card)?\.key/);
  assert.match(src, /foldsAs\(canvas\.folded, m\.card\.key\)/);
});

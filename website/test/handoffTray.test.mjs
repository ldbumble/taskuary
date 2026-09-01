import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const feed = readFileSync(fileURLToPath(new URL("../src/FeedView.jsx", import.meta.url)), "utf8");
const review = feed.slice(feed.indexOf("const ReviewCanvas"), feed.indexOf("const TalkItThrough"));

test("the Timeline keeps handoff behind one action instead of an always-open form", () => {
  assert.match(review, /<TrayBtn onClick=\{\(\) => setHandoff\(true\)\}[\s\S]*?>\s*Hand off<\/TrayBtn>/);
  assert.match(review, /<Drawer[^>]+open=\{handoff && !!sel\.TaskId\}/);
  assert.match(review, /\{handoff && sel\.TaskId && <Handoff/);
  assert.doesNotMatch(review, /<TrayGroupLabel[^>]*>HAND OFF<\/TrayGroupLabel>/);
});

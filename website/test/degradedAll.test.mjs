import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { degradedOf, isIncomplete, settlingNotice } from "../src/processingAll.js";

// The canonical All used to answer 409 with no rows whenever its membership census was behind or
// conflicted, so the Timeline swapped to the legacy /api/feed every time. The page now says what it
// could not group, and only one of those cases actually needs another transport.
test("a settled page claims nothing", () => {
  assert.equal(degradedOf({ items: [] }), null);
  assert.equal(isIncomplete({ items: [] }), false);
  assert.equal(settlingNotice({ items: [] }), "");
});

test("grouping behind, nothing missing: read it and say so", () => {
  const data = { coverage: { degraded: { reason: "reconciling", missing: 0, uncatalogued: {} } } };
  assert.equal(isIncomplete(data), false, "no transport swap for a census that is merely behind");
  assert.match(settlingNotice(data), /catching up/);
});

test("a conflict is named as one, because it does not clear on its own", () => {
  const data = { coverage: { degraded: { reason: "conflicted", missing: 0, conflicts: [{ code: "split" }] } } };
  assert.equal(isIncomplete(data), false);
  assert.match(settlingNotice(data), /conflict/);
});

test("entities that could not be grouped at all make the page incomplete", () => {
  const data = { coverage: { degraded: { reason: "reconciling", missing: 4, uncatalogued: { message: 4 } } } };
  assert.equal(isIncomplete(data), true, "rows really are absent - only the legacy transport has them");
  assert.equal(settlingNotice(data), "", "no reassuring line over a page that is missing mail");
});

test("the Timeline branches on the manifest, not on an error", () => {
  const view = readFileSync(new URL("../src/FeedView.jsx", import.meta.url), "utf8");
  assert.ok(view.includes("if (isIncomplete(data)) throw"), "incomplete still reaches the legacy fallback");
  assert.ok(view.includes("setAllFallbackNotice(settlingNotice(data))"),
    "and a page that is merely settling says so where the fallback banner used to");
});

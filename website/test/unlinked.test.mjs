import test from "node:test";
import assert from "node:assert/strict";
import { needsLink, UNLINKED_LINE } from "../src/unlinked.js";

const doc = (meta) => ({ querySelector: (q) => (meta && q.includes("taskuary-unlinked") ? {} : null) });
const store = (v) => ({ getItem: () => v });

test("an unkeyed page with no stored token says how to get in", () => {
  assert.equal(needsLink(doc(true), store(null)), true);
  assert.match(UNLINKED_LINE, /taskuary --link/);
});

test("a tab that already holds the token, or a keyed page, opens the app", () => {
  assert.equal(needsLink(doc(true), store("tok")), false);
  assert.equal(needsLink(doc(false), store(null)), false);
});

test("storage that refuses to be read counts as no token", () => {
  assert.equal(needsLink(doc(true), { getItem: () => { throw new Error("blocked"); } }), true);
});

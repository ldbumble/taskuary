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

test("a stored token the server refuses is dropped, and the page says how to get in instead of 'reload'", async () => {
  const { staleToken } = await import("../src/unlinked.js");
  let kept = "old";
  const st = { getItem: () => kept, removeItem: () => { kept = null; } };
  const refused = { response: { status: 401, data: { code: "unauthorized", detail: "x" } } };
  assert.equal(staleToken(refused, st), true);
  assert.equal(kept, null);
  assert.equal(needsLink(doc(true), st), true);
});

test("any other failure keeps the token", async () => {
  const { staleToken } = await import("../src/unlinked.js");
  let kept = "tok";
  const st = { getItem: () => kept, removeItem: () => { kept = null; } };
  for (const e of [{ response: { status: 403, data: { detail: "agents cannot do this" } } }, { response: { status: 401, data: {} } }, {}, null]) {
    assert.equal(staleToken(e, st), false);
  }
  assert.equal(kept, "tok");
  assert.equal(staleToken({ response: { status: 401, data: { code: "unauthorized" } } }, { removeItem: () => { throw new Error("blocked"); } }), true);
});

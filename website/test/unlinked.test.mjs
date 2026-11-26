import test from "node:test";
import assert from "node:assert/strict";
import { needsLink, UNLINKED_LINE } from "../src/unlinked.js";

const doc = (meta) => ({ querySelector: (q) => (meta && q.includes("taskuary-unlinked") ? {} : null) });
const store = (v) => ({ getItem: () => v });

test("an unkeyed page with no stored token says how to get in", () => {
  assert.equal(needsLink(doc(true), store(null)), true);
  assert.match(UNLINKED_LINE, /from its app/);
  assert.doesNotMatch(UNLINKED_LINE, /taskuary --|run /, "a command named on the page is one an agent that opens it runs (walk 19)");
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

test("a tab left open across a restart is refused with the old token: the new one the restart seeded is kept, and the tab reloads onto it", async () => {
  const { staleToken } = await import("../src/unlinked.js");
  let kept = "new";
  const st = { getItem: () => kept, removeItem: () => { kept = null; } };
  const refused = { config: { headers: { "X-Taskuary-Token": "old" } }, response: { status: 401, data: { code: "unauthorized" } } };
  assert.equal(staleToken(refused, st), "renewed");
  assert.equal(kept, "new", "the restart's token is never dropped by a tab that held the old one");
  assert.equal(needsLink(doc(true), st), false);
  // ...and the refused token being the stored one still drops it, as before
  assert.equal(staleToken({ ...refused, config: { headers: { "X-Taskuary-Token": "new" } } }, st), true);
  assert.equal(kept, null);
});

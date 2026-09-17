import test from "node:test";
import assert from "node:assert/strict";
import { coveredByReload } from "../src/funnelPile.js";

// A press of Next: the settle writes and emits at t=1000; the turn's own reload STARTS at t=1600.
// The debounced live reload that fires at t=2500 has nothing left to fetch.
test("an event that arrived before a forced load began is covered by that load", () => {
  assert.equal(coveredByReload({ firstAt: 1000, lastAt: 1000 }, 1600), true);
});

// A new mail landing at t=2000, after the reload began at t=1600, is NOT covered - the rail must refresh.
test("an event newer than the last forced load start is not covered", () => {
  assert.equal(coveredByReload({ firstAt: 1000, lastAt: 2000 }, 1600), false);
});

test("no meta (a hello, an old caller) and no forced load ever both mean: refresh", () => {
  assert.equal(coveredByReload(undefined, 1600), false);
  assert.equal(coveredByReload({ firstAt: 1000, lastAt: 1000 }, 0), false);
  assert.equal(coveredByReload({ type: "hello" }, 1600), false);
});

// Compared against the load's START, never its end: a load that began before the write and finished
// after it read stale rows.
test("a load that began before the event does not cover it, however late it finished", () => {
  assert.equal(coveredByReload({ firstAt: 1000, lastAt: 1000 }, 900), false);
});

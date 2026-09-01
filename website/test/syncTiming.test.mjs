import test from "node:test";
import assert from "node:assert/strict";
import { syncStatusDelay } from "../src/syncTiming.js";

test("sync status checks quietly when the scheduled refresh is far away", () => {
  assert.equal(syncStatusDelay({ nextAt: 600_000, now: 0 }), 30_000);
});

test("sync status watches closely around the scheduled refresh", () => {
  assert.equal(syncStatusDelay({ nextAt: 20_000, now: 0 }), 500);
  assert.equal(syncStatusDelay({ nextAt: 10_000, now: 20_000 }), 500);
});

test("an observed running sync is followed every two seconds", () => {
  assert.equal(syncStatusDelay({ running: true, nextAt: 600_000, now: 0 }), 2000);
});

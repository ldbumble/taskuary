import test from "node:test";
import assert from "node:assert/strict";


import { BURST_MS, burstsNow, pieceAt, piecesOf } from "../src/allDone.js";


// REACHING CLEAR (the owner, 2026-11-06): confetti once, on the way from rows to none - never on a reload or a rail already clear
test("the burst plays only on the way from rows to none", () => {
  assert.equal(burstsNow(3, 0), true);
  assert.equal(burstsNow(1, 0), true);
  assert.equal(burstsNow(null, 0), false, "a reload onto a clear rail stays quiet");
  assert.equal(burstsNow(0, 0), false, "an already clear rail drawn again stays quiet");
  assert.equal(burstsNow(2, 1), false);
  assert.equal(burstsNow(0, 2), false);
});

test("the pieces fly out and fade by the end of the burst", () => {
  const ps = piecesOf(20, 3);
  assert.equal(ps.length, 20);
  assert.deepEqual(piecesOf(20, 3), ps, "a seed draws the same burst");
  for (const p of ps) { assert.equal(pieceAt(p, 0).fade, 1); assert.equal(pieceAt(p, BURST_MS).fade, 0); }
  assert.ok(BURST_MS >= 1200 && BURST_MS <= 1800);
});

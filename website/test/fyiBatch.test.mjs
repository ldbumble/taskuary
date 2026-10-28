import assert from "node:assert/strict";
import test from "node:test";
import { FYI_HEADER, fyiBatchFor } from "../src/fyiBatch.js";

// SIX ON A DESKTOP, FOUR ON A SMALL SCREEN (the owner, 2026-10-28): a laptop under 800px tall or a phone reads four FYI together
test("the FYI batch follows the screen", () => {
  for (const [w, h, n] of [[1440, 900, 6], [1920, 1080, 6], [1280, 800, 6], [1366, 768, 4], [1280, 720, 4], [390, 844, 4], [600, 1000, 4]])
    assert.equal(fyiBatchFor(w, h), n, `${w}x${h}`);
  assert.equal(FYI_HEADER.toLowerCase(), "x-taskuary-fyi-batch", "the header taskuary/server.py fyi_screen reads");
});

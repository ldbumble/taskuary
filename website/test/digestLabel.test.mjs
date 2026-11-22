import { test } from "node:test";
import assert from "node:assert";


import { digestLabel } from "../src/digestLabel.js";

test("the digest is named by when it was written", () => {
  assert.equal(digestLabel("2026-11-02 09:00:00"), "MORNING DIGEST");
  assert.equal(digestLabel("2026-11-02 14:30:00"), "AFTERNOON DIGEST");
  assert.equal(digestLabel("2026-11-02 22:12:00"), "EVENING DIGEST");
  assert.equal(digestLabel(null, new Date(2026, 10, 2, 22, 12)), "EVENING DIGEST");
});

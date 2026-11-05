import test from "node:test";
import assert from "node:assert/strict";
import { whyFailed } from "../src/stepWhy.js";
test("a failed step opens on the line that says what went wrong", () => {
  assert.equal(whyFailed("cd C:/work\n$ python pull.py\nTraceback (most recent call last):\n  File \"pull.py\", line 3\nFileNotFoundError: no such file: lk.sql"),
    "Why: FileNotFoundError: no such file: lk.sql");
  assert.equal(whyFailed(""), "It stopped without saying why.");
});

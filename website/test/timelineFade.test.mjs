import test from "node:test";
import assert from "node:assert/strict";
import { FADE_MODES, fadeBand } from "../src/timelineFade.js";

test("the setting controls a viewport band, not row age", () => {
  assert.deepEqual(FADE_MODES, ["off", "gentle", "normal", "sharp"]);
  assert.equal(fadeBand("off"), null);
  assert.ok(fadeBand("gentle").height < fadeBand("normal").height);
  assert.ok(fadeBand("normal").height < fadeBand("sharp").height);
});

test("normal is the safe fallback for an unknown saved value", () => {
  assert.deepEqual(fadeBand(), fadeBand("normal"));
  assert.deepEqual(fadeBand("nonsense"), fadeBand("normal"));
});

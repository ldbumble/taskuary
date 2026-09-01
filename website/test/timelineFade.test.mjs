import test from "node:test";
import assert from "node:assert/strict";
import { FADE_MODES, ageOpacity, timelineOpacity } from "../src/timelineFade.js";

test("a fresh row is never dimmed, in any mode", () => {
  for (const mode of FADE_MODES) {
    assert.equal(ageOpacity(0, mode), 1, mode);
    assert.equal(ageOpacity(0.2, mode), 1, mode);
  }
});

test("off keeps every row at full brightness however old", () => {
  assert.equal(ageOpacity(1000, "off"), 1);
});

test("normal is the default fade", () => {
  assert.equal(ageOpacity(3), ageOpacity(3, "normal"));
  assert.notEqual(ageOpacity(3), ageOpacity(3, "sharp"));
});

test("each mode reaches a visibly different place at the same age", () => {
  // the whole reason the setting has four values: at three hours old they must not look alike
  const at3 = (m) => ageOpacity(3, m);
  assert.equal(at3("off"), 1);
  assert.ok(at3("gentle") > at3("normal"), "gentle dims less than normal");
  assert.ok(at3("normal") > at3("sharp"), "normal dims less than sharp");
  assert.ok(at3("sharp") < 0.75, "sharp is clearly quiet by three hours");
  assert.ok(at3("gentle") > 0.8 && at3("gentle") < 0.9, "gentle is visible but light within a morning");
});

test("nothing ever fades past its floor", () => {
  assert.equal(ageOpacity(1e6, "sharp"), 0.35);
  assert.equal(ageOpacity(1e6, "normal"), 0.5);
  assert.equal(ageOpacity(1e6, "gentle"), 0.68);
});

test("the curve only ever darkens as a row gets older", () => {
  for (const mode of ["gentle", "normal", "sharp"]) {
    let prev = 1;
    for (let h = 0; h <= 48; h += 0.25) {
      const o = ageOpacity(h, mode);
      assert.ok(o <= prev + 1e-9, `${mode} brightened at ${h}h`);
      prev = o;
    }
  }
});

test("an unparsed or future timestamp is shown, not hidden", () => {
  assert.equal(ageOpacity(0, "sharp"), 1);
  assert.equal(ageOpacity(-5, "sharp"), 1);      // clock skew must never dim a row
  assert.equal(ageOpacity(NaN, "sharp"), 1);
  assert.equal(ageOpacity(5, "nonsense"), 1);    // a mode the UI does not know about
});

test("filter results remain fully legible regardless of age or fade mode", () => {
  for (const mode of FADE_MODES) {
    assert.equal(timelineOpacity(1000, mode, true), 1, mode);
  }
  assert.equal(timelineOpacity(1000, "normal", false), ageOpacity(1000, "normal"));
});

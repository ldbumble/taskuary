import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const src = readFileSync(fileURLToPath(new URL("../src/ProductTour.jsx", import.meta.url)), "utf8");

test("the overlay is a dialog over the real chrome, not a second app", () => {
  assert.match(src, /role="dialog"/);
  assert.match(src, /aria-modal="true"/);
  assert.match(src, /zIndex: 1600/);
  assert.match(src, /from "\.\/productTour\.js"/);
  assert.match(src, /TOUR_STEPS/);
  assert.match(src, /Get started/);
  assert.match(src, /onClose\?\.\("skipped"\)/);
  assert.match(src, /onClose\?\.\("done"\)/);
  assert.match(src, /Escape/);
  assert.match(src, /ArrowRight/);
  assert.match(src, /ArrowLeft/);
  assert.doesNotMatch(src, /window\.confirm/);
});

test("the card wears the same mark and gradient as the rest of the chrome", () => {
  assert.match(src, /<TaskuaryMark/);
  assert.match(src, /background: GRADIENT/);
  assert.match(src, /Skip walkthrough/);
  assert.match(src, /dimRects\(hole/);
  assert.match(src, /data-tour=/);
});

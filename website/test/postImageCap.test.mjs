import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// A POST'S PICTURE IS A PREVIEW (the owner, 2026-11-05): capped, its press still opens it whole
test("the post card caps its picture and opens it whole on a press", () => {
  const card = read("ActionCard.jsx");
  assert.match(card, /const IMG_MAX = 180;/);
  assert.match(card, /height: IMG_MAX, objectFit: "contain"/);     // ...its room held from the first frame (2026-11-12)
  assert.match(card, /onClick=\{\(\) => setViewing\(pic\)\}/);
});

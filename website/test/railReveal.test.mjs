// The 2026-10-19 UI walk: Next put a report on the table while its row sat under the rail's fold - ringed where nobody could see it.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { revealBy } from "../src/railReveal.js";

const V = { top: 100, bottom: 460 };
test("the ringed rows are shown whole by the least scroll, and left alone when they already are", () => {
  assert.equal(revealBy(V, { top: 150, bottom: 204 }, 22, 75), 0, "in view: nothing moves");
  assert.equal(revealBy(V, { top: 403 + 100, bottom: 457 + 100 }, 22, 75), 557 - 385, "under the fold: up by exactly the overlap");
  assert.equal(revealBy(V, { top: 90, bottom: 144 }, 22, 0), -32, "under the sticky heading: down to clear it");
  assert.equal(revealBy(V, { top: 300, bottom: 900 }, 22, 75), 300 - 122, "taller than the room: its top, never past it");
});
test("the rail reveals the ring once per change of what is on the table, after the rows glide", () => {
  const src = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  assert.match(src, /const t = setTimeout\(\(\) => revealRing\(wrapRef\.current\), 620\);/);
  assert.match(src, /\}, \[tableKey\]\);/);
});

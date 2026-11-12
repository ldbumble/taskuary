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
// THE RAIL WALK (2026-11-12): a row clicked low in a scrolled rail grew its second line under the fold and the rail scrolled ~75px with the
// pointer on it - the row just pressed slid out from under it. A rail being pointed at is left where it is; Next and Back still reveal.
test("the ring is revealed when it moved from elsewhere, never while the pointer is on the rail", async () => {
  const { revealRing } = await import("../src/railReveal.js");
  const fake = (hover) => {
    const sc = { scrollTop: 0, matches: (q) => q === ":hover" && hover, getBoundingClientRect: () => ({ top: 100, bottom: 460 }), parentElement: { querySelector: () => null } };
    const row = { getBoundingClientRect: () => ({ top: 440, bottom: 497 }), closest: () => null };
    return { sc, wrap: { closest: () => sc, querySelectorAll: () => [row] } };
  };
  const off = fake(false); assert.equal(revealRing(off.wrap), 37); assert.equal(off.sc.scrollTop, 37, "Next or Back: the ring is brought into view");
  const on = fake(true); assert.equal(revealRing(on.wrap), 0); assert.equal(on.sc.scrollTop, 0, "a click: the rail under the pointer stays put");
});

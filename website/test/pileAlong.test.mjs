// The rail rides along with the answer (design B, 2026-09-17): a turn's `done` and a settle's reply
// carry the pile as the server left it after their writes, and the page HOLDS it - captures Next from
// it under the scope it will press with - instead of fetching the same rows again. A press of Next was
// two of those reloads at 1.5-2 s each: the visible gap between the old rows vanishing and the next
// four appearing.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { coveredByReload, heldSince } from "../src/funnelPile.js";

const view = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
const between = (from, to) => view.slice(view.indexOf(from), view.indexOf(to));

test("a held rail dates from when the server began reading it, never later than now", () => {
  const now = 1_000_000;
  assert.equal(heldSince({ generated_at: 999_000 }, now), 999_000, "the server's clock, when it is behind ours");
  assert.equal(heldSince({ generated_at: 1_000_500 }, now), now, "a clock ahead of ours must not cover a write the read did not see");
  assert.equal(heldSince({}, now), now);
  assert.equal(heldSince({ generated_at: "not a time" }, now), now);
  assert.equal(heldSince(null, now), now);
  // ...and that is the mark the live handler compares against: the turn's own writes (events before the
  // read) are covered; a write after the read began is not
  assert.equal(coveredByReload({ lastAt: 998_000 }, heldSince({ generated_at: 999_000 }, now)), true);
  assert.equal(coveredByReload({ lastAt: 999_500 }, heldSince({ generated_at: 999_000 }, now)), false);
});

test("landed holds the rail the turn brought and only falls back to its own load without one", () => {
  const landed = between("const landed = useCallback", "const ensureNextSelection");
  assert.match(landed, /if \(card && data\.pile\) holdPile\(data\.pile, nextSelectionScope\(only\.current, card\.key\)\)/,
    "the new table is excluded from the held scope - that is the scope the next press sends");
  assert.match(landed, /else \{ selectionRef\.current = null; loadPile\(true\); \}/);
  assert.doesNotMatch(landed, /say\(data\.say\); loadPile\(true\)/, "the unconditional reload after every turn is gone");
  const hold = between("const holdPile = useCallback", "const landed = useCallback");
  assert.match(hold, /forcedLoadStartedAt\.current = heldSince\(data\)/);
  assert.match(hold, /selectionRef\.current = captureNextSelection\(data, scope\)/);
  assert.match(hold, /setPile\(\(p\) => refreshPilePresentation\(p, data\)\)/);
});

test("All read, next: the settle brings the rail back and the walk takes it without a reload", () => {
  const done = between("const done = async (receipt)", "// Setting Taskuary up");
  assert.match(done, /verb: "done", only: only\.current/, "the settle learns the walk's scope so the rail comes back captured under it");
  assert.match(done, /\.data\?\.pile \|\| null/);
  assert.match(done, /advance\(pile\)/);
  const advance = between("const advance = (pile", "const done = async");
  assert.match(advance, /if \(pile\) holdPile\(pile, nextSelectionScope\(only\.current, null\)\)/, "the table is empty after a settle: nothing excluded");
  assert.match(advance, /pile \? 120 : 500/, "a rail in hand needs no half-second of grace");
  assert.ok(advance.indexOf("clearTable()") < advance.indexOf("holdPile("), "clearTable nulls the capture; the held one must land after it");
});

test("a typed next keeps the capture: the table did not change, so the token still names the pick", () => {
  const next = between('if (verb === "next") {', 'if (verb === "reply" && mid)');
  assert.doesNotMatch(next, /selectionRef\.current = null/);
  assert.match(next, /deferInChat\(\(\) => surfaceRef\.current\?\.\(\), 300\)/);
});

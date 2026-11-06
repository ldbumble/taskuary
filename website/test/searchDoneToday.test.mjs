// DONE TODAY (the owner, 2026-11-06): the tasks closed today, as a filter of the search box (and Ctrl K) only - never on the work rail.
// Pressed, the box asks the server for `done:today` beside the words typed (search.DONE_TODAY); a hit opens its task at a press.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const src = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the search box carries a Done today filter that asks the server for done:today", () => {
  const s = src("SearchEverything.jsx");
  assert.match(s, /const DONE_TODAY = "done:today";/);
  assert.match(s, /data-tq-search-today=\{today \? "on" : "off"\}/);
  assert.match(s, /api\.get\("\/api\/search", \{ params: \{ q: k \} \}\)/);
  assert.match(s, /if \(!today && !asks\(t\)\)/, "nothing typed still lists today's closed tasks");
  assert.match(s, /\}, \[q, today\]\);/);
  assert.match(s, /setToday\(false\); typed\.current = held\.current = "";/, "closing the box puts the filter down");
  assert.match(s, /else if \(h\.type === "task"\) onOpenTask\?\.\(h\.tid, h\);/, "a hit opens its task");
  const py = fs.readFileSync(new URL("../../taskuary/search.py", import.meta.url), "utf8");
  assert.match(py, /DONE_TODAY, N_DONE = 'done:today', 40/);
});

test("never on the work rail", () => {
  for (const f of ["FeedView.jsx", "feedFilters.js", "railStatus.js"]) assert.doesNotMatch(src(f), /done:today|Done today/i, f);
});

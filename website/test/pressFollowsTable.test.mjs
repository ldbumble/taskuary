// ONE PRESS WALKS ON (the owner, 2026-10-26: Next said "The list moved while that was loading - press it again" - "the list changed while
// you pressed next should be fixed as well"): the rail read a press waits on settled the table under it, and the press stopped.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { nextSelectionScope as sc, pressFollowsTable } from "../src/funnelPile.js";

const view = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
const A = { key: "msg:4", tid: 12 }, B = { key: "msg:9", tid: 30 };

test("a table the server cleared, or the same task under its new key, is followed - the press captures again", () => {
  assert.equal(pressFollowsTable(sc(null, "msg:4"), sc(null, null), A, null), true, "the server said the item is gone");
  assert.equal(pressFollowsTable(sc(null, "msg:4"), sc(null, "agent:12"), A, { key: "agent:12", tid: 12 }), true, "handed to an agent");
  assert.equal(pressFollowsTable(sc(null, "msg:4"), sc(null, "agent:12"), A, { key: "agent:12", tid: "12" }), true, "a number read as text");
});

test("another item put up, or a filter changed under the press, is still refused", () => {
  assert.equal(pressFollowsTable(sc(null, "msg:4"), sc(null, "msg:9"), A, B), false, "Next past an item never seen would skip it");
  assert.equal(pressFollowsTable(sc(null, null), sc(null, "msg:9"), null, B), false, "an empty table that got an item");
  assert.equal(pressFollowsTable(sc(null, "msg:4"), sc(null, "msg:7"), { key: "msg:4" }, { key: "msg:7" }), false, "no task on either: keys decide");
  assert.equal(pressFollowsTable(sc(null, "msg:4"), sc("view:{}", null), A, null), false, "the owner changed the filter");
  assert.equal(pressFollowsTable(sc(null, "msg:4"), sc(null, null, true), A, null), false);
  assert.equal(pressFollowsTable(null, sc(null, null), A, null), false);
});

test("surface captures again a bounded number of times and only then says the list moved", () => {
  const surface = view.slice(view.indexOf("const surface = useCallback"), view.indexOf("useEffect(() => { surfaceRef.current"));
  assert.match(surface, /for \(let round = 0; ; round \+= 1\) \{/);
  assert.match(surface, /if \(ours && scopeMoved && round < 2 && pressFollowsTable\(scope, activeScope, was, currentRef\.current\)\) continue;/);
  assert.ok(surface.indexOf("pressFollowsTable(") < surface.indexOf("setErr((m) => m || \"The list moved"), "followed before it is refused");
  // a read in flight for another table is waited out, not shared: it is dropped when it lands and its successor is this scope's
  const ensure = view.slice(view.indexOf("const ensureNextSelection = useCallback"), view.indexOf("const noteLine = useCallback"));
  assert.match(ensure, /if \(pileFlight\.current\) await pileFlight\.current;\s*else await loadPileRef\.current\?\.\(true\);/);
  assert.match(ensure, /attempt < 3/);
});

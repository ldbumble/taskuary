// NEXT IS "SHOW ME THE NEXT THING" (the owner, 2026-10-26: "i hate the next list changed. No one cares. Think about it from user
// perspective"): a list moving under a press is absorbed by the page - captured again, retried with the server's fresh pick - and never
// becomes a line asking for another press. One press is still one move.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const view = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
const surface = view.slice(view.indexOf("const surface = useCallback"), view.indexOf("useEffect(() => { surfaceRef.current"));

test("a rail read that moves the table under the press is captured again, bounded, then the server picks", () => {
  assert.match(surface, /for \(let round = 0; round < 3; round \+= 1\) \{/);
  assert.match(surface, /if \(!scopeMoved\) break;\s*scope = activeScope; capture = null;/);
  assert.match(surface, /let navigation = capture \? nextSelectionBody\(capture\) : \{ \.\.\.scope \};/);
  for (const said of ["The list moved while that was loading", "Next is still refreshing"]) assert.ok(!view.includes(said), `no "${said}" line`);
  // a new chat or a reset is the owner's own doing: the one quiet return left
  assert.match(surface, /if \(epoch !== chatEpoch\.current \|\| resettingRef\.current\) \{ turnFlight\.current = false; setBusy\(false\); dropCarried\(\); return; \}/);
  // a read in flight for another table is waited out, not shared: it is dropped when it lands and its successor is this scope's
  const ensure = view.slice(view.indexOf("const ensureNextSelection = useCallback"), view.indexOf("const noteLine = useCallback"));
  assert.match(ensure, /if \(pileFlight\.current\) await pileFlight\.current;\s*else await loadPileRef\.current\?\.\(true\);/);
});

test("the server's stale refusal is retried at once - its fresh pick, then its own - and only a real one is said", () => {
  assert.match(surface, /for \(let tries = 0; ; tries \+= 1\) \{\s*try \{ data = await turn\(\{ mode: "next", key, leaving, \.\.\.navigation \}\); break; \}/);
  assert.match(surface, /\["navigation_in_progress", "already_completed", "outcome_uncertain"\]\.includes\(g\.reason\)/, "one press, one move");
  assert.match(surface, /if \(real \|\| tries >= 2 \|\| epoch !== chatEpoch\.current\) throw e;/);
  assert.match(surface, /const fresh = tries === 0 \? captureNextSelection\(g, scope\) : null;/);
  assert.ok(!/blind && selectionGuardDetail/.test(surface), "blind and non-blind presses alike");
  assert.ok(!/press Next again/i.test(view.slice(view.indexOf("const errText"), view.indexOf("const DEMO_SAID"))), "no 'press Next again' for a list change");
});

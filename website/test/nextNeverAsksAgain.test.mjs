// NEXT IS "SHOW ME THE NEXT THING" (the owner, 2026-10-26: "i hate the next list changed. No one cares. Think about it from user
// perspective"): a list moving under a press is absorbed by the page - captured again, retried with the server's fresh pick - and never
// becomes a line asking for another press. One press is still one move.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const view = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
const surface = view.slice(view.indexOf("const surface = useCallback"), view.indexOf("useEffect(() => { surfaceRef.current"));

test("a press is one move with no capture to go stale: the row on screen goes with it, and no line asks for another press", () => {
  assert.match(surface, /const fromKey = how === "start" \? null : key \? leaving \|\| null : leaving \|\| currentRef\.current\?\.key \|\| null;/);
  assert.match(surface, /const press = `p\$\{Date\.now\(\)\}/, "a press id: a retry is the same answer, one line (railwalk)");
  assert.doesNotMatch(view, /selection_revision|expected_next_key|ensureNextSelection|selectionGuardDetail/);
  for (const said of ["The list moved while that was loading", "Next is still refreshing"]) assert.ok(!view.includes(said), `no "${said}" line`);
  assert.ok(!/press Next again/i.test(view.slice(view.indexOf("const errText"), view.indexOf("const DEMO_SAID"))), "no 'press Next again' for a list change");
});

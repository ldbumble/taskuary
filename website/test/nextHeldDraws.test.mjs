import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import { heldStep } from "../src/funnelPile.js";

// A NEXT PRESSED ON THE ROW A PRESS DREW, WHILE THAT PRESS IS OUT (the owner, 2026-11-02: "when you hit next the one you are on, task or
// report, does not disappear right away"): the second press reads the walk one step further - the row after the one below and whether Next
// reads the one below - and puts its row down and draws the next at its press, never after the first answer
// (browser/next-leaves-at-press.test.mjs holds every answer 2.5 s and watches it happen).
const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");

test("the walk's word one step further: a task stays, a report and an fyi batch are read, a row off the line knows nothing", () => {
  const walk = { on: "task:1", below: "task:2", below_reads: false, then: "report:7" };
  assert.deepEqual(heldStep(walk, "task:2"), { known: true, reads: false, gone: [], then: "report:7" });
  assert.deepEqual(heldStep({ ...walk, below: "report:7", below_reads: true, then: "report:8" }, "report:7"),
    { known: true, reads: true, gone: ["report:7"], then: "report:8" });
  assert.deepEqual(heldStep({ ...walk, below: "fyis:msg:1,msg:2", below_reads: true, then: null }, "fyis:msg:1,msg:2").gone,
    ["fyis:msg:1,msg:2", "msg:1", "msg:2"], "a batch takes its members off with it");
  assert.deepEqual(heldStep(walk, "task:9"), { known: false, reads: false, gone: [], then: null }, "a row picked off the walk's line: only folded");
  assert.equal(heldStep(null, "task:2").known, false, "no walk read yet");
});

test("a held Next draws at its press, its press runs from the row it put down, and the first answer never puts that row back", () => {
  assert.match(view, /next: \(\) => \{ if \(\(picking \|\| flight\?\.drawn\) && busy\) holdNext\(\);/);
  assert.match(view, /if \(c\?\.verb === "next" && busy && flight\?\.drawn && !resetting\) \{ holdNext\(\); return; \}/);
  assert.match(view, /if \(c\.verb === "next"\) \{ surface\(null, null, heldRef\.current\?\.from \|\| key, !item\); return; \}/);
  assert.match(view, /if \(h && card\?\.key === h\.from\) \{/, "the first answer fills the passed row's line, not the table");
  // ...and a failed press under it, or Back, gives back what it took
  assert.match(view, /if \(heldRef\.current\) \{ nextHeld\.current = false; cancelHeld\(false\); \}/);
  assert.match(view, /backHeld\.current = true; nextHeld\.current = false; cancelHeld\(\);/);
});

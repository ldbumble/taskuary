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

// BACK THE SAME WAY (the owner, 2026-11-02: "the Back button takes way too long, not like the Next button"): from the row a Back drew, the row
// above that (walk.above_then); from the row a Next drew, the row it left - or the one above when Next reads it. Never across a close or a
// pick, which this cannot see past. And Next on the row a Back drew comes back down to the row that Back left (browser/back-at-press.test.mjs)
test("the walk's word one step up: Back from a Back's row, from a Next's, and Next from a Back's", () => {
  const walk = { on: "task:2", above: "task:1", above_then: "task:0", above_reads: false, below: "task:3", reads: false, then: "report:7" };
  assert.deepEqual(heldStep(walk, "task:1", true, "back"), { known: true, reads: false, gone: [], then: "task:0" }, "Back, Back: two up");
  assert.equal(heldStep({ ...walk, above_then: null }, "task:1", true, "back").known, false, "at the top: nothing to draw");
  assert.equal(heldStep(walk, "task:3", true, "next").then, "task:2", "Next, Back: the row Next left");
  assert.equal(heldStep({ ...walk, on: "report:5", reads: true }, "task:3", true, "next").then, "task:1", "...or above it, when Next read it");
  assert.equal(heldStep(walk, "task:3", true, "leave").known, false, "a close takes its row off the line: not seen past");
  assert.equal(heldStep(walk, "task:1", true, "next").known, false, "the press out is not the one that drew this row");
  assert.deepEqual(heldStep(walk, "task:1", false, "back"), { known: true, reads: false, gone: [], then: "task:2" }, "Back, Next: back down");
  assert.deepEqual(heldStep({ ...walk, above: "report:4", above_reads: true }, "report:4", false, "back").gone, ["report:4"], "...reading a report it passes");
});

test("a held Next draws at its press, its press runs from the row it put down, and the first answer never puts that row back", () => {
  assert.match(view, /next: \(\) => \{ if \(busy && !resetting\) holdMove\("next"\);/);
  assert.match(view, /if \(c\?\.verb === "next" && busy && !resetting\) \{ holdMove\("next"\); return; \}/);
  assert.match(view, /if \(c\.verb === "next"\) \{ surface\(null, null, heldRef\.current\?\.from \|\| key, !item\); return; \}/);
  assert.match(view, /if \(h && card\?\.key === h\.from\) \{/, "the first answer fills the passed row's line, not the table");
  // ...and a failed press under it gives back what it took; a Next and a Back held over one press take each other back
  assert.match(view, /if \(heldRef\.current\) \{ nextHeld\.current = backHeld\.current = false; cancelHeld\(false\); \}/);
  assert.match(view, /if \(other\.current\) \{ other\.current = false; cancelHeld\(\); return; \}/);
});

test("Back draws the row above at its press and is never refused as a press already out", () => {
  assert.match(view, /: how === "back" && fromKey && walkNow\?\.on === fromKey && walkNow\.above && !walkNow\.above\.startsWith\("fyis:"\) \? walkNow\.above/);
  assert.match(view, /if \(how === "back" && !data\.item && data\.top\) \{ undraw\(\);/, "the top after all: the row drawn comes down");
  const row = readFileSync(fileURLToPath(new URL("../src/actionRow.js", import.meta.url)), "utf8");
  assert.match(row, /v\?\.group !== "next" && v\?\.group !== "back"\) flying\.set/, "a second Back reaches the walk's own hold");
});

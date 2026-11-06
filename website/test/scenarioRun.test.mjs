import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// What the scenario run (2026-11-06: many messages, many tasks, three widths) found off by a pixel or a word, pinned

// A FOLDED TURN'S ONE LINE is cut where it ends - its whole words on hover too, not only a press away
test("the folded What I did line carries its whole words as its title", () => {
  assert.match(read("AgentSummary.jsx"), /<Box component="summary" title=\{did\} sx=\{\{ \.\.\.HEAD, mt: 0, cursor: "pointer", whiteSpace: "nowrap"/);
});

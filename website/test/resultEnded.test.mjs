// A run a restart cut off says so where its Result would be (the desktop run, 2026-11-04): it read "It ended without a written result - open
// the Result for what it did" over a Result with nothing in it. The story's own sentence stands there instead.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const rec = fs.readFileSync(new URL("../src/AgentRecord.jsx", import.meta.url), "utf8");
const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");

test("an interrupted run's Result says how it ended", () => {
  assert.match(rec, /export const ResultSummary = \(\{ taskId, stamp, pages = \[\], said = "", ended = "", onRecord = null \}\)/);
  assert.match(rec, /\{ended \|\| "It ended without a written result - open the Result for what it did\."\}/);
  assert.match(page, /ended=\{story\?\.kind === "interrupted" \? story\.line \|\| "" : ""\}/);
});

// The dead-end walk (../deadend_check.mjs) on every browser run, held against a baseline that only goes DOWN.
//
// The walk found more than one session could fix (2026-10-17), so it lands measuring: a rule over its count in
// deadend-baseline.json fails the run - a new dead end is a regression - and a rule under it says so, so the fix that
// cleared it lowers the number in the same commit. The goal is every count at 0, and then this file holds that.
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const baseline = JSON.parse(readFileSync(path.join(here, "deadend-baseline.json"), "utf8"));

test("the walk leaves the owner alone no more often than it did", { timeout: 2400000 }, () => {
  const run = spawnSync(process.execPath, [path.join(here, "..", "deadend_check.mjs"), "--json", "--port", "7798"],
    { encoding: "utf8", timeout: 2350000, windowsHide: true });     // four passes: walk, sweep, faults, cards
  const out = JSON.parse((run.stdout || "").trim().split("\n").pop() || "{}");
  assert.ok(out.counts, `the walk did not finish: ${run.stdout}${run.stderr}`);
  const worse = Object.entries(out.counts).filter(([r, n]) => n > (baseline[r] || 0));
  assert.deepEqual(worse, [], `more dead ends than the baseline:\n${out.found.join("\n")}`);
  const better = Object.entries(baseline).filter(([r, n]) => n > (out.counts[r] || 0));
  if (better.length) console.log(`fewer than the baseline - lower deadend-baseline.json: ${JSON.stringify(Object.fromEntries(better.map(([r]) => [r, out.counts[r] || 0])))}`);
});

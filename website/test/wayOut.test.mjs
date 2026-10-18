// The ways past a failure the rebuilt walk found missing (2026-10-18): an undo confirms as Take it back, a send nobody can confirm
// offers Send anyway and Mark done on the card, a failed start on the task page draws its fix - every word read from the list.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe } from "../src/proposalCard.js";
import { label } from "../src/buttons.js";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("a receipt's undo card confirms with Take it back and never shows its _undo flag", () => {
  const d = describe({ kind: "task.defer", label: "Remind me", params: { until: "2026-10-20", _undo: true } });
  assert.equal(d.confirm, label("take_back"));
  assert.ok(!d.params.some(([k]) => k.includes("undo")), JSON.stringify(d.params));
  assert.notEqual(describe({ kind: "task.defer", label: "Remind me", params: { until: "2026-10-20" } }).confirm, label("take_back"));
});

test("the card's unconfirmed send offers Send anyway and Mark done, by their names on the list", () => {
  const s = src("ReviewDecision.jsx");
  assert.match(s, /btn\("approve", "unknown"\)/);
  assert.match(s, /decide\("approve", true\)/);
  assert.match(s, /unconfirmed && r\.TaskId/);
});

test("a failed start on the task page draws its ways past it", () => {
  const s = src("TaskPage.jsx");
  assert.match(s, /<FailWays fail=\{startFail\}/);
  assert.match(src("failure.jsx"), /label\("try_again"\)[\s\S]*label\("report_bug"\)/);
});

// A CLOSED TASK OPENED FROM SEARCH IS ONLY OPENED (the owner, 2026-11-06): Search's open ran Reopen task by itself, and a task the owner had only
// opened stood under a greyed "Reopening…". It opens closed, in its chat - typing to it reopens it - and Reopen's busy word never outlives its press.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("opening a closed task from Search reopens nothing, and Reopening… always clears", () => {
  assert.doesNotMatch(src("SearchEverything.jsx"), /markReopen|reopenFromSearch/);
  const page = src("TaskPage.jsx");
  assert.doesNotMatch(page, /takeReopen|REOPEN_MARKED/);
  assert.match(page, /cap = setTimeout\(done, REOPEN_MAX_MS\)/);
  assert.match(page, /finally \{ clearTimeout\(cap\); done\(\); \}/);
});

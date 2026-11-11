// THE GENERAL-AGENT DESKTOP STRESS TEST'S FOLLOW-UPS (2026-11-03), each pinned where it is decided.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("with Developer mode off the New sheet is a general agent's alone: no live session, no repository, no coding tool", () => {
  const s = src("NewSheet.jsx");
  assert.match(s, /how = devMode \? howPick : "general"/);
  assert.match(s, /\{devMode && <Box>\s*<Label>Who works it<\/Label>/);
  assert.match(src("ui.jsx"), /devMode: data\.developer_mode \?\? false/, "off until the server says so - no coding UI while settings load (audit 2026-11-05)");
});

test("an Approve on a held step keeps the agent's pane: the Advisor's pick never re-keys the page", () => {
  const s = src("TaskPage.jsx");
  assert.doesNotMatch(s, /mainKey = `[^`]*\|\$\{advised(Held)?\}\|/);
  assert.doesNotMatch(s, /advisedHeld/);
});

test("the agent's state is said once, by the task header's pill - live or stopped, the pane heading carries no chip of its own", () => {
  const s = src("TaskPage.jsx");
  assert.match(s, /chip=\{resultShown \? shareBadge : null\} tone=\{PALETTE\.sage\}/);
  assert.doesNotMatch(s, /<LifecycleChip kind="agent"|<StoryChip /);
});

// ...and in the dock only: in a task's chat the note alone drew an empty "Along the way" fold under the head (the side-by-side walk, 2026-11-11)
test("'Started <the agent>' opens the dock conversation's first turn only", () => {
  const s = src("GeneralWorkspace.jsx");
  assert.match(s, /const keepStart = dock && !runMessages\.some\(\(m\) => m\.role === "assistant"\);/);
  assert.match(s, /stepsPart\(events, \{ answer: reply \|\| "", keepStart \}\)/);
});

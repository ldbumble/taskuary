// New has a Report tab and a Workflow tab (the owner, 2026-10-15: "we need 2, one for reports and one for workflows"):
// describe it, Build it, and the draft opens on Reports filled in - the same box Reports has, no second form.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canvasRequestFromHash } from "../src/canvasLinks.js";
import { DRAFT_HASH, handDraft, onDraftHanded, takeDraft } from "../src/draftHandoff.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

// THE DESCRIBE BOX IS THE CHAT'S NOW (the owner, 2026-10-30): each tab brings its builder up and opens the Assistant on it - or by hand
test("a report or routine the Assistant wrote up on New is a door to its builder and the chat", () => {
  const src = read("NewSheet.jsx");
  assert.match(src, /<SetupWithAi kind=\{kind\} words=\{kind === initialKind \? initialText : ""\} onOpen=\{\(\) => \{ onClose\?\.\(\); openAppLink\(NEW_HASH\[kind\]\); \}\} \/>/);
  assert.match(src, />Set it up by hand<\/Button>/);
  assert.doesNotMatch(src, /<Composer/);
  assert.doesNotMatch(src, /"repeat"/);
  const door = read("SetupWithAi.jsx");
  assert.match(door, /onClick=\{\(\) => startSetup\(kind, words, onOpen\)\}/);
  for (const [k, h] of [["report", "report=new"], ["dashboard", "report=new-dashboard"], ["workflow", "report=new-agent"]]) assert.match(door, new RegExp(`${k}: "${h}"`));
});

test("each draft opens on its own shelf, on the canvas too", () => {
  assert.deepEqual(canvasRequestFromHash(`#${DRAFT_HASH.workflow}`).state, { section: "workflows", open: "draft" });
  assert.deepEqual(canvasRequestFromHash(`#${DRAFT_HASH.report}`).state, { section: "reports", open: "draft" });
});

test("a draft waits for Reports, and an open Reports hears it at once - taken once", () => {
  handDraft("workflow", { title: "x" }, { explain: "y" });
  assert.deepEqual(takeDraft(), { kind: "workflow", config: { title: "x" }, meta: { explain: "y" } });
  assert.equal(takeDraft(), null);
  let heard = 0; const off = onDraftHanded(() => { heard += 1; });
  handDraft("report", {}, {}); off(); handDraft("report", {}, {});
  assert.equal(heard, 1);
  takeDraft();
  const view = read("ReportsView.jsx");
  assert.match(view, /take\(\);\s*\n\s*return onDraftHanded\(take\);/);
});

// THE ASSISTANT'S PREFILL LANDS IN THE FORM (the owner, 2026-10-29: "Wrote it into New - Build it there starts it" over blank fields):
// concierge._new's `new` - its words and its `routine` {coding, repo, skill} - rides the browse state into New → Routine's own box
test("a routine the Assistant wrote up opens New → Routine with its words, carried into the chat's ask", () => {
  const canvas = read("CanvasBrowse.jsx"), sheet = read("NewSheet.jsx");
  assert.match(canvas, /initialText=\{state\?\.text \|\| ""\}/);
  assert.match(canvas, /initialRoutine=\{state\?\.routine \|\| null\}/);
  assert.match(canvas, /JSON\.stringify\(state\?\.routine \|\| ""\)/, "a new prefill remounts the sheet, so its fields are the new ones");
  assert.match(sheet, /initialRoutine = null, madeOf = "" \}\) \{/);
  assert.match(read("SetupWithAi.jsx"), /`Help me set up \$\{WHAT\[kind\] \|\| WHAT\.report\}\$\{String\(words \|\| ""\)\.trim\(\) \? `: \$\{String\(words\)\.trim\(\)\}` : ""\}`/);
});

// STRAIGHT INTO THE BUILDER (owner-approved, 2026-11-12): "a routine that lists vendors with no invoice" came back as New's Routine card with
// Set up with AI and Set it up by hand - a middle card, and Set up with AI asked the Assistant the same thing again. A report, dashboard or
// routine the Assistant wrote up opens its builder with the setup already asked, once per line, through Set up with AI's own press
test("a report, dashboard or routine the Assistant wrote up goes straight into its builder, the setup asked once", async () => {
  const { REPEATS, goesStraight } = await import("../src/newTask.js");
  assert.deepEqual(REPEATS, ["report", "dashboard", "workflow"]);
  for (const k of REPEATS) assert.equal(goesStraight(k, 31), true, k);
  assert.equal(goesStraight("workflow", null), false, "a card nobody wrote up stays the card");
  assert.equal(goesStraight("agent", 31), false);
  const sheet = read("NewSheet.jsx"), door = read("SetupWithAi.jsx");
  assert.match(door, /export const startSetup = \(kind, words, onOpen\) => \{ onOpen\?\.\(\); openHelp\(helpAsk\(kind, words\), \{ wait: 700 \}\); \};/);
  assert.match(door, /onClick=\{\(\) => startSetup\(kind, words, onOpen\)\}/);
  assert.match(sheet, /const straight = goesStraight\(kind, line\) && kind === initialKind;/);
  assert.match(sheet, /if \(!straight \|\| straightGone\.current\) return;\s*\n\s*straightGone\.current = true; if \(firstPressOf\(line\)\) startSetup\(kind, initialText, toBuilder\);/);
  // ...and no card is drawn on its way there: the New card never flashes before the builder
  assert.ok(sheet.indexOf("straightGone.current = true") < sheet.indexOf("if (inline && !open) return null;"));
  assert.match(sheet, /if \(straight\) return null;/);
});

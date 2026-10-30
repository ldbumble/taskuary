// New has a Report tab and a Workflow tab (the owner, 2026-10-15: "we need 2, one for reports and one for workflows"):
// describe it, Build it, and the draft opens on Reports filled in - the same box Reports has, no second form.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canvasRequestFromHash } from "../src/canvasLinks.js";
import { DRAFT_HASH, handDraft, onDraftHanded, takeDraft } from "../src/draftHandoff.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

// THE DESCRIBE BOX IS THE CHAT'S NOW (the owner, 2026-10-30): each tab brings its builder up and opens the Assistant on it - or by hand
test("Report and Workflow are tabs on New, each a door to its builder and the chat", () => {
  const src = read("NewSheet.jsx");
  assert.match(src, /key: "report", +mark: "📊", label: "Report"/);
  assert.match(src, /key: "workflow", mark: "🔁", label: "Routine"/);
  assert.match(src, /<SetupWithAi kind=\{kind\} words=\{kind === initialKind \? initialText : ""\} onOpen=\{\(\) => \{ onClose\?\.\(\); openAppLink\(NEW_HASH\[kind\]\); \}\} \/>/);
  assert.match(src, />Set it up by hand<\/Button>/);
  assert.doesNotMatch(src, /<Composer/);
  assert.doesNotMatch(src, /"repeat"/);
  const door = read("SetupWithAi.jsx");
  assert.match(door, /onClick=\{\(\) => \{ onOpen\?\.\(\); openHelp\(helpAsk\(kind, words\), \{ wait: 700 \}\); \}\}/);
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
  assert.match(sheet, /initialRoutine = null \}\) \{/);
  assert.match(read("SetupWithAi.jsx"), /`Help me set up \$\{WHAT\[kind\] \|\| WHAT\.report\}\$\{String\(words \|\| ""\)\.trim\(\) \? `: \$\{String\(words\)\.trim\(\)\}` : ""\}`/);
});

// New has a Report tab and a Workflow tab (the owner, 2026-10-15: "we need 2, one for reports and one for workflows"):
// describe it, Build it, and the draft opens on Reports filled in - the same box Reports has, no second form.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canvasRequestFromHash } from "../src/canvasLinks.js";
import { DRAFT_HASH, handDraft, onDraftHanded, takeDraft } from "../src/draftHandoff.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("Report and Workflow are tabs on New, each the Reports describe box", () => {
  const src = read("NewSheet.jsx");
  assert.match(src, /key: "report", +mark: "📊", label: "Report"/);
  assert.match(src, /key: "workflow", mark: "🔁", label: "Routine"/);
  // ...and a workflow ask the composer judged to be a report opens on the report shelf (the owner, 2026-10-18)
  assert.match(src, /<Composer kind=\{kind\} initial=\{kind === initialKind \? initialText : ""\} initialRuns=\{kind === initialKind \? initialRoutine : null\} onDraft=\{\(config, meta\) => \{ const k = meta\?\.verdict === "report" \? "report" : kind; handDraft\(k, config, meta\); onClose\?\.\(\); openAppLink\(DRAFT_HASH\[k\]\); \}\} \/>/);
  assert.doesNotMatch(src, /"repeat"/);
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
test("a routine the Assistant wrote up opens New → Routine with its words, repository and skill filled in", () => {
  const canvas = read("CanvasBrowse.jsx"), sheet = read("NewSheet.jsx"), box = read("Composer.jsx");
  assert.match(canvas, /initialText=\{state\?\.text \|\| ""\}/);
  assert.match(canvas, /initialRoutine=\{state\?\.routine \|\| null\}/);
  assert.match(canvas, /JSON\.stringify\(state\?\.routine \|\| ""\)/, "a new prefill remounts the sheet, so its fields are the new ones");
  assert.match(sheet, /initialRoutine = null \}\) \{/);
  assert.match(box, /const \[ask, setAsk\] = useState\(initial\)/);
  assert.match(box, /coding: !!\(initialRuns\?\.coding \|\| initialRuns\?\.repo \|\| initialRuns\?\.skill\), repo: initialRuns\?\.repo \|\| "", skill: initialRuns\?\.skill \|\| ""/);
  // ...and what was picked goes to the builder, laid over its draft (workflows.with_runs)
  assert.match(box, /runs: \{ coding: true, cwd, skill: runs\.skill \}/);
  assert.match(box, /data-tq-routine-repo/); assert.match(box, /"data-tq-routine-skill"/);
});

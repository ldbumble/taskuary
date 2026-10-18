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
  assert.match(src, /key: "workflow", mark: "🔁", label: "Workflow"/);
  // ...and a workflow ask the composer judged to be a report opens on the report shelf (the owner, 2026-10-18)
  assert.match(src, /<Composer kind=\{kind\} onDraft=\{\(config, meta\) => \{ const k = meta\?\.verdict === "report" \? "report" : kind; handDraft\(k, config, meta\); onClose\?\.\(\); window\.location\.hash = DRAFT_HASH\[k\]; \}\} \/>/);
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

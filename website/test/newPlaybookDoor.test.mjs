// A PLAYBOOK HAS ITS OWN DOORS (the owner, 2026-10-22: "this is not playbook ui? ... no new playbook ui either??"): New has a Playbook
// tab beside Report and Workflow, Reports has + New playbook beside + New report and + New workflow, and both open the one road to a
// playbook there is - the Playbooks shelf's New playbook dialog (NewPlaybookDialog), with the words New was given.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canvasRequestFromHash } from "../src/canvasLinks.js";
import { NEW_PB, askPlaybook, takePlaybookAsk } from "../src/playbookOpen.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("New has a Playbook tab after Report and Workflow, its press handing the words to the shelf's New playbook", () => {
  const src = read("NewSheet.jsx");
  assert.ok(src.indexOf('key: "workflow"') < src.indexOf('key: "playbook", mark: "📖", label: "Playbook"'));
  assert.match(src, /askPlaybook\(about, true\); onClose\?\.\(\); openAppLink\(`report=\$\{NEW_PB\}`\);/);
  assert.match(src, /kind === "playbook" \? "Set up with AI"/);
});

test("Reports offers + New playbook beside + New report and + New workflow, opening New playbook on its shelf", () => {
  const view = read("ReportsView.jsx");
  // ...and + New dashboard second, beside + New report (the owner, 2026-10-23)
  assert.match(view, /\{ key: "new-dashboard", label: DASH\.new \}, \{ key: "new-agent", label: "\+ New routine" \},\s*\{ key: NEW_PB, label: "\+ New playbook" \}\]/);
  assert.match(view, /key === NEW_PB \? \{ section: "playbooks", open: null, newPb: Date\.now\(\) \}/);
  assert.match(view, /<NewPlaybook key=\{browseState\.newFor \|\| browseState\.newPb \|\| ""\}[^>]*asked=\{!!browseState\.newPb\}/);
});

test("New's link lands on the Playbooks shelf with New playbook asked for - each ask numbered, so a second opens it again", () => {
  assert.equal(NEW_PB, "new-playbook");
  assert.deepEqual(canvasRequestFromHash(`#report=${NEW_PB}`, 4).state, { section: "playbooks", open: null, newPb: 5 });
  assert.deepEqual(canvasRequestFromHash("#report=playbooks").state, { section: "playbooks", open: null });
});

test("the words wait for the shelf and are taken once; the dialog starts from them only when Set up with AI was pressed on New", () => {
  askPlaybook("when Erin asks for the weekly numbers, gather them for my review", true);
  assert.deepEqual(takePlaybookAsk(), { text: "when Erin asks for the weekly numbers, gather them for my review", start: true });
  assert.equal(takePlaybookAsk(), null);
  const shelf = read("PlaybookShelf.jsx"), dlg = read("NewPlaybookDialog.jsx");
  assert.match(shelf, /initialText=\{ask\?\.text \|\| ""\} autoStart=\{!!ask\?\.start\}/);
  assert.match(dlg, /useState\(initialText\.trim\(\) \? "scratch" : ""\)/);
  assert.match(dlg, /if \(autoStart && initialText\.trim\(\) && !pressed\.current\) \{ pressed\.current = true; start\(\); \}/);
});

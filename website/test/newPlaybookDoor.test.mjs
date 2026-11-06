// A PLAYBOOK HAS ITS OWN DOORS (the owner, 2026-10-22: "this is not playbook ui? ... no new playbook ui either??"): New has a Playbook
// tab beside Report and Workflow, and it opens the one road to a playbook there is - the Playbooks shelf's New playbook dialog
// (NewPlaybookDialog), with the words New was given. The shelf is About you's since 2026-11-06, no longer the Reports page's.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canvasRequestFromHash } from "../src/canvasLinks.js";
import { NEW_PB, askPlaybook, takePlaybookAsk } from "../src/playbookOpen.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("New has a Playbook tab after Report and Workflow, its press handing the words to the shelf's New playbook", () => {
  const src = read("NewSheet.jsx");
  assert.ok(src.indexOf('key: "workflow"') < src.indexOf('key: "playbook", mark: "📖", label: "Playbook"'));
  assert.match(src, /askPlaybook\(about, true\); onClose\?\.\(\); openAppLink\(`about=\$\{NEW_PB\}`\);/);
  assert.match(src, /kind === "playbook" \? "Set up with AI"/);
});

test("About you's Playbooks shelf holds New playbook, asked open when New sent the words; Reports offers none", () => {
  const view = read("SettingsView.jsx");
  assert.match(view, /<NewPlaybook key=\{browseState\.newFor \|\| browseState\.newPb \|\| ""\}[^>]*asked=\{!!browseState\.newPb\}/);
  assert.doesNotMatch(read("ReportsView.jsx"), /NEW_PB|NewPlaybook|"Playbooks"/);
});

test("New's link lands on the Playbooks shelf with New playbook asked for - each ask numbered, so a second opens it again", () => {
  assert.equal(NEW_PB, "new-playbook");
  assert.deepEqual(canvasRequestFromHash(`#about=${NEW_PB}`, 4), { kind: "browse", area: "about", state: { section: "playbooks", open: null, newPb: 5 }, n: 4 });
  assert.deepEqual(canvasRequestFromHash(`#report=${NEW_PB}`, 4).state, { section: "playbooks", open: null, newPb: 5 }, "the old link too");
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

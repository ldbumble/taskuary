// PLAYBOOKS LIVE ONLY ON THE REPORTS PAGE (the owner, 2026-10-21): Reports / Workflows / Playbooks, each playbook with its own on/off
// switch; Settings is for regular configuration and offers none of it.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { pbOpen } from "../src/playbookOpen.js";

const src = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the Reports page has a Playbooks shelf beside Reports and Workflows, one open in its editor", () => {
  const r = src("ReportsView.jsx");
  assert.match(r, /\{ key: "playbooks", label: "Playbooks", n: pbs\.books\.length \}/);
  assert.match(r, /<PlaybookRow b=\{b\}/);
  assert.match(r, /<PlaybookDetail key=\{pbSlug\} slug=\{pbSlug\} onGone=\{back\} \/>/);
  assert.equal(pbOpen("pb:weekly-close"), "weekly-close");
  assert.equal(pbOpen(17), null);
});

test("each playbook switches on and off where it is listed", () => {
  const s = src("PlaybookShelf.jsx");
  assert.match(s, /api\.put\(`\/api\/playbooks\/\$\{slug\}\/enabled`, \{ on \}\)/);
  assert.match(s, /<Switch size="small" checked=\{on\}/);
});

test("Delete is at once, and Recently deleted under the shelf restores it", () => {
  const d = src("DocsView.jsx"), s = src("PlaybookShelf.jsx"), r = src("ReportsView.jsx");
  assert.doesNotMatch(d, /Delete playbook\?|confirmDeletePb|<Dialog /);
  assert.match(s, /api\.post\(`\/api\/playbooks\/\$\{slug\}\/restore`\)/);
  assert.match(r, /<PlaybooksDeleted items=\{pbs\.deleted\} onRestore=\{pbs\.restore\} \/>/);
});

test("Settings offers no playbooks any more", () => {
  const v = src("SettingsView.jsx");
  assert.doesNotMatch(v, /label: "Playbooks"/);
  assert.doesNotMatch(v, /g:playbooks|new-playbook|NewPlaybookDialog/);
});

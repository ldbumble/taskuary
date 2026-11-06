// PLAYBOOKS LIVE ON ABOUT YOU (the owner, 2026-11-06), beside the docs and what was learned - "how you do your job" - each playbook with
// its own on/off switch. The Reports page (their home from 2026-10-21) and Settings offer none of it.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { pbOpen } from "../src/playbookOpen.js";

const src = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("About you has a Playbooks shelf beside You, Docs and Memory, one open in its editor", () => {
  const v = src("SettingsView.jsx");
  assert.match(v, /const mine = about \? \["you", "docs", "playbooks", "memory"\]/);
  assert.match(v, /<PlaybookRow b=\{b\}/);
  assert.match(v, /<PlaybookDetail key=\{pbSlug\} slug=\{pbSlug\} onGone=\{pbBack\} \/>/);
  assert.match(v, /const pbs = usePlaybooks\(about && !!browse\);/, "Settings itself never reads them");
  assert.equal(pbOpen("pb:weekly-close"), "weekly-close");
  assert.equal(pbOpen(17), null);
});

test("each playbook switches on and off where it is listed", () => {
  const s = src("PlaybookShelf.jsx");
  assert.match(s, /api\.put\(`\/api\/playbooks\/\$\{slug\}\/enabled`, \{ on \}\)/);
  assert.match(s, /<Switch size="small" checked=\{on\}/);
});

test("Delete is at once, and Recently deleted under the shelf restores it", () => {
  const d = src("DocsView.jsx"), s = src("PlaybookShelf.jsx"), v = src("SettingsView.jsx");
  assert.doesNotMatch(d, /Delete playbook\?|confirmDeletePb|<Dialog /);
  assert.match(s, /api\.post\(`\/api\/playbooks\/\$\{slug\}\/restore`\)/);
  assert.match(v, /<PlaybooksDeleted items=\{pbs\.deleted\} onRestore=\{pbs\.restore\} \/>/);
});

test("the Reports page and Settings' own sections offer no playbooks", () => {
  const r = src("ReportsView.jsx"), v = src("SettingsView.jsx");
  assert.doesNotMatch(r, /usePlaybooks|PlaybookRow|key: "playbooks"/);
  assert.match(v, /: \["config", "profiles", "policies", \.\.\.\(devMode \? \["audit"\] : \[\]\), "updates"\];/);
  assert.doesNotMatch(v, /g:playbooks|NewPlaybookDialog/);
});

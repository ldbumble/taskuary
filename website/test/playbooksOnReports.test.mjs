// PLAYBOOKS LIVE ONLY ON THE REPORTS PAGE (the owner, 2026-10-21): Reports / Workflows / Playbooks, each playbook with its own on/off
// switch; Settings is for regular configuration and offers none of it. About you held them a few hours on 2026-11-06 and gave them back
// (the owner: "it's more about how you work, not about you").
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

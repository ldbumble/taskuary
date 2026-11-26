// SKILLS LIVE ONLY ON THE REPORTS PAGE (the owner, 2026-10-21): Reports / Workflows / Skills, each skill with its own on/off
// switch; Settings is for regular configuration and offers none of it. About you held them a few hours on 2026-11-06 and gave them back
// (the owner: "it's more about how you work, not about you").
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { pbOpen } from "../src/skillOpen.js";

const src = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the Reports page has a Skills shelf beside Reports and Workflows, one open in its editor", () => {
  const r = src("ReportsView.jsx");
  assert.match(r, /\{ key: "skills", label: "Skills", n: pbs\.books\.length \}/);
  assert.match(r, /<SkillRow b=\{b\}/);
  assert.match(r, /<SkillDetail key=\{pbSlug\} slug=\{pbSlug\} onGone=\{back\} \/>/);
  assert.equal(pbOpen("pb:weekly-close"), "weekly-close");
  assert.equal(pbOpen(17), null);
});

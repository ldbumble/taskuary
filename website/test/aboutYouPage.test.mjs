// ONE PAGE ABOUT THE OWNER (the owner, 2026-11-06: "general things you care about, how you do your job, personality, goals"): About you,
// opened from the avatar in the top bar's corner - You, Docs and Memory - with Memory as plain sentences over LEARNED.md, never its tags.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { fromWhere, provenance, sentence } from "../src/memorySentences.js";

const src = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("About you is a page of its own, drawn by SettingsView's about area", () => {
  const b = src("CanvasBrowse.jsx");
  assert.match(b, /area === "about" && <SettingsView key="about" area="about"/);
  assert.match(b, /about: "About you"/);
  assert.match(src("TaskHubPage.jsx"), /About: "about"/);
  assert.doesNotMatch(src("FeedView.jsx"), /about: PersonOutlineIcon/, "no sidebar line");
  assert.match(src("SettingsView.jsx"), /const mine = about \? \["you", "docs", "memory"\]/);
});

test("Memory shows LEARNED.md as one sentence per line with Keep / Wrong / Forget, through the existing mark road", () => {
  const m = src("MemoryLines.jsx");
  assert.match(m, /api\.get\("\/api\/learned\/graph"\)/);
  assert.match(m, /api\.post\("\/api\/learned\/mark", \{ key, how \}\)/);
  assert.match(m, /<MarkRow marks=\{marksFor\(l\)\}/);
  assert.doesNotMatch(m, /l\.score|s:\{|l\.key\}<|evidence\.length/, "no score, id or evidence count on the line");
  assert.match(src("SettingsView.jsx"), /section === "memory" \? \[\{ key: "memory", node: <MemoryLines \/> \}\]/);
});

test("a line's sentence carries no tag, stamp or markdown, and ends like a sentence", () => {
  assert.equal(sentence("prefers short replies"), "Prefers short replies.");
  assert.equal(sentence("- 2026-10-03: answers **Erin** first [s:4 | ev: rv12 | seen: 2026-10-05 | k: ab12]"), "Answers Erin first.");
  assert.equal(sentence("closes the books on the 5th [memory:k9]"), "Closes the books on the 5th.");
  assert.equal(sentence("Wants `weekly` numbers?"), "Wants weekly numbers?");
  assert.equal(sentence("  "), "");
});

test("under it, faint: when it was learned and from what - or that the owner wrote it", () => {
  const l = { evidence: [{ kind: "verdict", date: "2026-10-09 10:00:00" }, { kind: "review", date: "2026-10-03 08:00:00" }, { kind: "verdict", date: null }] };
  assert.match(provenance(l), /^learned Oct 3 from your verdicts and your reviews$/);
  assert.equal(provenance({ own: true }), "you wrote this");
  assert.equal(provenance({ evidence: [], seen: "" }), "");
  assert.equal(fromWhere([{ kind: "message" }, { kind: "task" }, { kind: "idea" }, { kind: "message" }]), "mail you answered, what you did on tasks and more");
});

test("every old address of Docs and Memory still lands - and the Assistant's page map names the page, Playbooks on Reports", async () => {
  const words = JSON.parse(fs.readFileSync(new URL("../../taskuary/words.json", import.meta.url), "utf8")).places;
  for (const k of ["about", "docs", "memory"]) assert.match(words[k].name, /^About you → /, k);
  assert.equal(words.memory.href, "#about=memory");
  assert.equal(words.playbooks.name, "Reports → Playbooks");
  const { canvasRequestFromHash } = await import("../src/canvasLinks.js");
  for (const k of ["about", "docs", "memory"]) assert.equal(canvasRequestFromHash(words[k].href).area, "about", k);
  assert.equal(canvasRequestFromHash(words.playbooks.href).area, "reports");
});

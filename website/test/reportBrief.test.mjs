// THE END OF DAY CHECKUP, READ AS ITS SHAPE (reportBrief.js): roll-ups, groups of bullets, a closing line - invented people throughout.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { briefItem, briefOf } from "../src/reportBrief.js";

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");
const EOD = `Done today: settled the AP cutover date and approved the agency invoices; 1 meeting invite handled.
Tomorrow: the census export move and Ray's schema sign-off.

**What I accomplished today**
- ✉️ ✅ Erin Blake — AP cutover — confirmed Thursday and shared the checklist.
- 🗓️ 📅 ✅ Paula Vance — AP cutover dry run — accepted for Wednesday 10:00.

### Focus for tomorrow
- 📌 🔍 Migrate the census export off the old portal — the old portal goes read-only on Monday.

A good day: the cutover is settled.`;

test("a brief reads as roll-ups, its groups of bullets and a closing line", () => {
  const b = briefOf(EOD);
  assert.deepEqual(b.rollups.map(([k]) => k), ["Done today", "Tomorrow"]);
  assert.deepEqual(b.groups.map((g) => [g.title, g.items.length]), [["What I accomplished today", 2], ["Focus for tomorrow", 1]]);
  assert.deepEqual(b.closing, ["A good day: the cutover is settled."]);
  assert.deepEqual(b.notes, []);
});

test("a bullet splits into its source mark, its status and who, what and the gist", () => {
  const i = briefItem("🗓️ 📅 ✅ Paula Vance — AP cutover dry run — accepted for Wednesday 10:00.");
  assert.deepEqual([i.src, i.status, i.who, i.what, i.gist], ["🗓️", ["meeting", "done"], "Paula Vance", "AP cutover dry run", "accepted for Wednesday 10:00."]);
  const two = briefItem("📌 🔍 Migrate the census export — goes read-only on Monday");
  assert.deepEqual([two.src, two.status, two.who, two.what, two.gist], ["📌", ["next"], "Migrate the census export", "", "goes read-only on Monday"]);
  assert.equal(briefItem("just words").gist, "just words");
});

test("the server's line on a connection it could not read is a note above the brief, not a roll-up", () => {
  const b = briefOf(`Not read this run: Outlook - signed out\n${EOD}`);
  assert.deepEqual(b.notes, ["Not read this run: Outlook - signed out"]);
  assert.equal(b.rollups.length, 2);
});

test("a report without the shape stays markdown", () => {
  assert.equal(briefOf("## Repos\n- org/app: 12 stars"), null);
  assert.equal(briefOf("Done today: little.\nTomorrow: the budget."), null);
  assert.equal(briefOf(""), null);
});

test("a report of words with the shape is drawn as the brief, on the table only", () => {
  const ac = src("assistantCards.jsx");
  assert.match(ac, /const brief = report && !morning && !rows && briefOf\(text\);/);
  assert.match(ac, /if \(brief\) return <ReportBrief brief=\{brief\}/);
});

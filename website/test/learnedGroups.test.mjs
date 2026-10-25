// WHAT TASKUARY KNOWS, BY SUBJECT (slice 6 of the memory redesign, 2026-10-25): Visualize groups the lines by the five sections with who
// really reads each, the people lines under their person with a link to that person's page where one exists, and Keep / Wrong / Forget
// on each line and on What changed - your own line only Forget, a line already put down none.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SECTIONS, byPerson, changeMarks, groupLines, marksFor, personDoc } from "../src/learnedGroups.js";

const g = {
  sections: SECTIONS,
  lines: [
    { key: "erin", text: "Erin Blake (erin@northwind.example) is your manager", status: "live", section_slug: "people", subject: "erin@northwind.example" },
    { key: "ray", text: "Payroll questions go to Ray Colton (ray@northwind.example)", status: "live", section_slug: "people", subject: "ray@northwind.example" },
    { key: "erin2", text: "You answer Erin within the hour", status: "live", section_slug: "people", subject: "erin@northwind.example", own: true },
    { key: "close", text: "Month-end close comes first", status: "live", section_slug: "care", subject: "" },
    { key: "fri", text: "Vendor renewals wait for Friday", status: "hypothesis", section_slug: "watching" },
    { key: "hide", text: "Hide PhishGuard newsletters", status: "proposed", section_slug: "proposed" },
  ],
};

test("the five subjects in order, each saying who reads it, then Watching and Proposed", () => {
  const gs = groupLines(g);
  assert.deepEqual(gs.map((s) => s.slug), ["people", "care", "work", "promises", "bring", "watching", "proposed"]);
  assert.equal(gs[0].reads, "read by triage (priority only) · drafts · the Advisor · the Assistant · agents");
  assert.deepEqual(gs[1].lines.map((l) => l.key), ["close"]);
  assert.deepEqual(gs[5].lines.map((l) => l.key), ["fri"]);
  assert.ok(gs.every((s) => !/rides into every prompt/.test(s.reads)), "no reader is said to read what it does not");
  assert.deepEqual(groupLines({ lines: [] }).map((s) => s.slug).slice(0, 5), SECTIONS.map((s) => s.slug), "an older server's page still has the five");
});

test("your people sit under the person they are about, with their page linked only where it exists", () => {
  const ppl = groupLines(g)[0].people;
  assert.deepEqual(ppl.map((p) => [p.subject, p.lines.map((l) => l.key)]), [["erin@northwind.example", ["erin", "erin2"]], ["ray@northwind.example", ["ray"]]]);
  assert.equal(personDoc("erin@northwind.example", [{ name: "person-erin@northwind.example" }]), "person-erin@northwind.example");
  assert.equal(personDoc("ray@northwind.example", [{ name: "person-erin@northwind.example" }]), "");
  assert.deepEqual(byPerson([{ subject: "" }, { subject: "a@x.example" }]).map((p) => p.subject), ["a@x.example", ""], "lines naming nobody last");
});

test("Keep / Wrong / Forget: all three on a learned line, only Forget on yours, none on a line already put down", () => {
  assert.deepEqual(marksFor(g.lines[0]), ["keep", "wrong", "forget"]);
  assert.deepEqual(marksFor(g.lines[2]), ["forget"]);
  assert.deepEqual(changeMarks({ key: "erin", newest: true, standing: "in_use" }), ["keep", "wrong", "forget"]);
  assert.deepEqual(changeMarks({ key: "erin", newest: false, standing: "in_use" }), [], "once per line, on its newest row");
  for (const st of ["wrong", "forgotten", "closed", "retired", "gone"]) assert.deepEqual(changeMarks({ key: "x", newest: true, standing: st }), []);
  assert.deepEqual(changeMarks({ key: "x", newest: true, standing: "own" }), ["forget"], "your own line: Forget alone");
});

test("Visualize and What changed both carry the marks, through the one endpoint, and say why when one does not take", () => {
  const viz = readFileSync(new URL("../src/LearnedView.jsx", import.meta.url), "utf8");
  const docs = readFileSync(new URL("../src/DocsView.jsx", import.meta.url), "utf8");
  for (const src of [viz, docs]) {
    assert.match(src, /api\.post\("\/api\/learned\/mark", \{ key, how \}\)/);
    assert.match(src, /role="alert"/, "a mark that did not take says why, by its line");
  }
  assert.match(viz, /Connect an AI to learn how you work/);
  assert.doesNotMatch(viz, /rides into every prompt/);
  assert.match(docs, /<LearnedView onChanged=\{load\} people=\{people\} onPerson=\{openPerson\} \/>/);
});

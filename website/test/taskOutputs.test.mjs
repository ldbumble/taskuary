// A file the agent made for its task is a file the owner can open (taskOutputs.js): Codex's citation marker, the made-up
// /outputs/TQ-n/ link and a bare path into the task's folder each become a chip through /api/task-outputs; a path anywhere
// else stays plain text.
import test from "node:test";
import assert from "node:assert/strict";
import { deliverables, family, isWorking, outputOf, outputRefs, outputRow, outputUrl, plainCitations, uncited } from "../src/taskOutputs.js";

const HOME = "C:/Users/alex/.taskuary/scratch/outputs";

test("Codex's citation marker becomes a chip and leaves the words", () => {
  const text = `I built the comparison.\n\n:codex-file-citation{path="${HOME}/TQ-0017/vendor comparison.xlsx" artifact_kind="workbook" purpose="output"}\n\nIt has two sheets.`;
  const got = outputRefs(text, 17);
  assert.deepEqual(got.files, ["vendor comparison.xlsx"]);
  assert.doesNotMatch(got.text, /codex-file-citation|artifact_kind/);
  assert.equal(got.text, "I built the comparison.\n\nIt has two sheets.");
});

test("the made-up /outputs/ link becomes a chip, its words kept and its dead address gone", () => {
  const got = outputRefs("Here it is: [Download the spreadsheet](http://127.0.0.1:7787/outputs/TQ-0017/vendor%20comparison.xlsx)", 17);
  assert.deepEqual(got.files, ["vendor comparison.xlsx"]);
  assert.equal(got.text, "Here it is: Download the spreadsheet");
  assert.doesNotMatch(got.text, /7787|\/outputs\//);
  assert.deepEqual(outputRefs("[x](/outputs/TQ-17/sub/a.csv)", 17).files, ["sub/a.csv"]);
});

test("a bare path into the task's folder becomes a chip under its own name", () => {
  const got = outputRefs(`Saved to ${HOME.replace(/\//g, "\\")}\\TQ-0017\\summary.pdf.`, 17);
  assert.deepEqual(got.files, ["summary.pdf"]);
  assert.equal(got.text, "Saved to `summary.pdf`.");
  assert.deepEqual(outputRefs(`file:///${HOME}/TQ-0017/a.png`, 17).files, ["a.png"]);
});

test("a path to another task, out of the folder, or anywhere else is plain text and never a chip", () => {
  const other = outputRefs(`[the file](http://127.0.0.1:7787/outputs/TQ-0018/x.xlsx) and :codex-file-citation{path="${HOME}/TQ-0018/y.xlsx"}`, 17);
  assert.deepEqual(other.files, []);
  assert.doesNotMatch(other.text, /\]\(|codex-file-citation/);         // not a link either: no click into a neighbour's file
  assert.match(other.text, /the file/);
  for (const bad of [`${HOME}/TQ-0017/../TQ-0018/x.xlsx`, `/outputs/TQ-0017/../../config.toml`, "C:/Windows/win.ini",
    `${HOME}/TQ-0017/a.xlsx:stream`, "https://example.com/outputs/TQ-0017/a.xlsx"])
    assert.equal(outputOf(bad, 17), null, bad);
  const plain = outputRefs("See [the site](https://northwind.example/report) and C:/Users/alex/Documents/notes.txt", 17);
  assert.deepEqual(plain.files, []);
  assert.equal(plain.text, "See [the site](https://northwind.example/report) and C:/Users/alex/Documents/notes.txt");
});

test("each file is chipped once, in the order it was named", () => {
  const got = outputRefs(`:codex-file-citation{path="${HOME}/TQ-0017/b.xlsx"}\n[b](/outputs/TQ-0017/b.xlsx) ${HOME}/TQ-0017/a.csv`, 17);
  assert.deepEqual(got.files, ["b.xlsx", "a.csv"]);
});

test("a chip resolves through the real route, and says so when the file is not there", () => {
  assert.equal(outputUrl(17, "sub/vendor comparison.xlsx"), "/api/task-outputs/17/sub/vendor%20comparison.xlsx");
  const listed = [{ id: "output:a.xlsx", path: "a.xlsx", name: "a.xlsx", url: "/api/task-outputs/17/a.xlsx", preview: "sheet", kind: "output" }];
  assert.equal(outputRow(17, "a.xlsx", listed), listed[0]);
  const gone = outputRow(17, "b.pdf", listed);
  assert.equal(gone.missing, true);
  assert.equal(gone.preview, "pdf");
  assert.equal(outputRow(17, "b.pdf", null).missing, false);              // listing not loaded yet: not called missing
});

test("the foot lists the task's files no answer names, so none is drawn twice", () => {
  const listed = [{ path: "a.xlsx" }, { path: "b.csv" }];
  assert.deepEqual(uncited(listed, ["[the book](/outputs/TQ-0017/a.xlsx)", "nothing here"], 17), [{ path: "b.csv" }]);
  assert.deepEqual(uncited(listed, ["[their book](/outputs/TQ-0018/a.xlsx)"], 17), listed);
  assert.deepEqual(uncited(undefined, [], 17), []);
});

test("anywhere else a citation is shown, it reads as the file's name", () => {
  assert.equal(plainCitations(`Done: :codex-file-citation{path="${HOME}/TQ-0017/a.xlsx" artifact_kind="workbook"}`), "Done: `a.xlsx`");
});

// ONE OF EACH (the owner, 2026-10-28: "it looks like it created a million attachments"): nine versions of one workbook, its helper script,
// its log and a temp file are one deliverable - the newest - with eight earlier versions behind it and three working files apart
test("v1..v9 and scratch files list once, with 8 earlier versions", () => {
  const at = (i) => `2026-10-27 10:${String(i).padStart(2, "0")}:00`;
  const rows = [...Array(9)].map((_, i) => ({ kind: "output", name: `pricing comparison v${i + 1}.xlsx`, path: `pricing comparison v${i + 1}.xlsx`, at: at(i + 1) }))
    .concat([{ kind: "output", name: "build_sheet.py", path: "build_sheet.py", at: at(20) }, { kind: "output", name: "run.log", path: "run.log", at: at(21) },
      { kind: "output", name: "rates.csv", path: "tmp/rates.csv", at: at(22) }, { kind: "output", name: "summary.pdf", path: "summary.pdf", at: at(5) },
      { kind: "shown", name: "chart.png", created_at: at(3) }]);
  const { made, working } = deliverables(rows);
  assert.deepEqual(made.map((r) => r.name), ["pricing comparison v9.xlsx", "summary.pdf", "chart.png"]);
  assert.equal(made[0].earlier.length, 8);
  assert.equal(made[0].earlier[0].name, "pricing comparison v8.xlsx");
  assert.deepEqual(working.map((r) => r.path).sort(), ["build_sheet.py", "run.log", "tmp/rates.csv"]);
  // the same rule as outputs.family
  assert.deepEqual(new Set(["Vendor pricing v9.xlsx", "vendor_pricing_final.xlsx", "vendor pricing (2).xlsx", "vendor-pricing-20261027-1530.xlsx",
    "drafts/vendor pricing draft.xlsx"].map(family)), new Set(["vendor pricing.xlsx"]));
  assert.equal(new Set(["budget 2025.xlsx", "budget 2026.xlsx", "region 1.csv", "region 2.csv"].map(family)).size, 4);
  assert.ok(!isWorking("summary.pdf") && isWorking("cache/x.json"));
});

test("an older version of a file an answer names is not one more file at the foot", () => {
  const listed = [outputRow(17, "plan_v2.md", []), outputRow(17, "plan_v1.md", []), outputRow(17, "raw costs.csv", [])];
  assert.deepEqual(uncited(listed, [`Done: ${HOME}/TQ-0017/plan_v2.md`], 17).map((r) => r.path), ["raw costs.csv"]);
});

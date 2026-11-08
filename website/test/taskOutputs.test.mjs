// A file the agent made for its task is a file the owner can open (taskOutputs.js): Codex's citation marker, the made-up
// /outputs/TQ-n/ link and a bare path into the task's folder each become a chip through /api/task-outputs; a path anywhere
// else stays plain text.
import test from "node:test";
import assert from "node:assert/strict";
import { deliverables, family, forTurn, isWorking, outputOf, outputRefs, outputRow, outputUrl, plainCitations, shownOnce, turnFiles, uncited } from "../src/taskOutputs.js";

test("a bare path to a name with spaces is that whole file, not a file called by its first word (stress test 2026-11-02)", () => {
  const listed = [{ path: "Open tasks 2026-11-02.xlsx", name: "Open tasks 2026-11-02.xlsx", kind: "output" }];
  const text = "The Excel file is ready: **C:\\Users\\alex\\.taskuary\\scratch\\outputs\\TQ-0077\\Open tasks 2026-11-02.xlsx**\n\nYou have 4 open tasks.";
  const got = outputRefs(text, 77, listed);
  assert.deepEqual(got.files, ["Open tasks 2026-11-02.xlsx"]);
  assert.equal(got.text, "The Excel file is ready: **`Open tasks 2026-11-02.xlsx`**\n\nYou have 4 open tasks.");
  assert.deepEqual(uncited(listed, [text], 77), []);
  assert.deepEqual(outputRefs(text, 77).files, ["Open"]);   // without the listing the old cut stands - the page always passes it
});

test("a bold path keeps its bold outside the file's name (stress test 2026-11-02)", () => {
  const got = outputRefs("Saved: **C:/Users/alex/.taskuary/scratch/outputs/TQ-0077/report.xlsx**.", 77);
  assert.deepEqual(got.files, ["report.xlsx"]);
  assert.equal(got.text, "Saved: **`report.xlsx`**.");
});

test("a file the answer names and also showed is one card, open - the shown copy is not drawn again (stress test 2026-11-02)", () => {
  const shown = [{ id: 7, name: "desk.svg", kind: "shown" }, { id: 8, name: "chart.png", kind: "shown" }];
  const { isShown, rest } = shownOnce(["desk.svg"], shown);
  assert.equal(isShown("desk.svg"), true);
  assert.equal(isShown("notes.md"), false);
  assert.deepEqual(rest.map((p) => p.id), [8]);
  assert.deepEqual(shownOnce([], undefined).rest, []);
});

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

// "TQ-0012 % Collected all-in-one v9.xlsx" is a real name an agent gave a workbook. A path on disk is its name as written - decoded, or
// cut at a '#', it named a file that is not there - while a link's target is a URL: decoded, its query and fragment cut first
test("a name with '%', '#' or an accent is the file it names, cited or linked", () => {
  for (const name of ["TQ-0012 % Collected all-in-one v9.xlsx", "Q3 #2 rates.csv", "Résumé – Gail Moreno.md", "100%25 done.txt"]) {
    const address = outputUrl(12, name).replace("/api/task-outputs/12/", "/outputs/TQ-0012/");
    assert.deepEqual(outputRefs(`:codex-file-citation{path="${HOME}/TQ-0012/${name}"}`, 12).files, [name], name);
    assert.deepEqual(outputRefs(`[it](${address})`, 12).files, [name], name);
    assert.deepEqual(outputRefs(`[it](http://127.0.0.1:7787${address}?x=1#top)`, 12).files, [name], name);
    assert.equal(decodeURIComponent(outputUrl(12, name).split("/").pop()), name);
  }
});

test("the task's folder and its files named bare become code spans the chat opens; code spans and other folders stay as written", () => {
  const B = String.fromCharCode(92), Q = String.fromCharCode(96), win = (...p) => p.join(B);
  const dir = win("C:", "Users", "alex", ".taskuary", "scratch", "outputs", "TQ-1348", "");
  const listed = [{ path: "Private balance audit.xlsx", name: "Private balance audit.xlsx" }];
  const { text, files } = outputRefs(`Files are in ${dir} :\n- Private balance audit.xlsx`, 1348, listed);
  assert.ok(text.includes(Q + dir + Q), text);
  assert.ok(text.includes(`- ${Q}Private balance audit.xlsx${Q}`), text);
  assert.deepEqual(files, ["Private balance audit.xlsx"]);
  // already in a code span: left exactly as it is, never wrapped twice
  const coded = `Files are in ${Q}${dir}${Q}.`;
  assert.equal(outputRefs(coded, 1348, []).text, coded);
  // another task's folder is not this task's link
  assert.ok(!outputRefs(`see ${win("C:", "x", "scratch", "outputs", "TQ-1349", "")} now`, 1348, []).text.includes(Q));
});

test("each turn shows the file as it made it; the newest turn the file itself (the owner, 2026-11-07: same file with revisions)", () => {
  const now = { id: "output:tools.md", path: "tools.md", name: "tools.md", kind: "output", url: "/api/task-outputs/8/tools.md", after: "comment-9" };
  const then = { ...now, id: "output:tools.md@3", url: "/api/task-outputs/8/tools.md?turn=3", turn: "comment-3", after: "comment-3" };
  const listed = [now], versions = [then];
  assert.deepEqual(forTurn(listed, versions, "comment-3"), [then]);              // turn 1 reads the copy it left
  assert.deepEqual(forTurn(listed, versions, "comment-9"), [now]);               // ...the newest turn the file as it is now
  assert.equal(forTurn(listed, undefined, "comment-3"), listed);
  const words = "Here is the comparison: `tools.md`";
  assert.deepEqual(turnFiles({ listed: forTurn(listed, versions, "comment-3"), id: "comment-3", words, tid: 8 }).map((f) => f.url), [then.url]);
  assert.deepEqual(turnFiles({ listed: forTurn(listed, versions, "comment-9"), id: "comment-9", words, tid: 8 }).map((f) => f.url), [now.url]);
  // ...and a file since deleted is still there under the turn that made it
  assert.deepEqual(forTurn([], versions, "comment-3"), [then]);
});

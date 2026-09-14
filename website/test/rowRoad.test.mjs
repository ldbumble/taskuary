import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { roadOf, roadOfCard } from "../src/timelineState.js";

// The tag on a Timeline row is TRIAGE's word - the one the row's own Triage tab highlights - and
// nothing else (the owner, 2026-09-07: "the tag on the row should match what the triage shows
// nothing else"). It used to be the attention lane, which is about what is waiting NOW, so every
// finished row read "fyi" whatever triage had said: a question triage sent to Review wore the same
// word as a newsletter.
test("the row's word is the road triage took", () => {
  assert.equal(roadOf({ RouteReason: "triage: fyi - automated notice" }), "fyi");
  assert.equal(roadOf({ RouteReason: "triage: reply_only - Hindy asks a simple question", TaskId: 404 }), "reply");
  assert.equal(roadOf({ RouteReason: "triage: task - fix the export", TaskId: 7, TaskKind: "coding" }), "coding");
  assert.equal(roadOf({ RouteReason: "triage: task - weigh the quotes", TaskId: 8, TaskKind: "general" }), "general");
  assert.equal(roadOf({ RouteReason: "triage: task - sign it yourself", TaskId: 9, TaskKind: "task" }), "task");
});

test("a reply keeps its word after the task closes, and an unjudged row claims none", () => {
  // the case from the screenshot: task done, nothing waiting, and triage had said reply_only
  assert.equal(roadOf({ RouteReason: "triage: reply_only - a familiarity question", TaskId: 404,
                        TaskStatus: "done", Lane: "fyi" }), "reply");
  assert.equal(roadOf({ TaskKind: "note", TaskId: 5 }), null, "your own note was judged by nobody");
  assert.equal(roadOf({}), null, "nothing classified it, so the row claims no road");
});

// The rail's pill is the same rule read off a pile card, which names the two fields differently
// (funnel._item): triaging while the AI decides, then what it decided, in work and timeline alike.
test("a pile card gets the same word as the timeline row it came from", () => {
  assert.equal(roadOfCard({ route: "triage: reply_only - a question", tid: 404, task_kind: "reply" }), "reply");
  assert.equal(roadOfCard({ route: "triage: task - fix the export", tid: 7, task_kind: "coding" }), "coding");
  assert.equal(roadOfCard({ route: "triage: fyi - a newsletter" }), "fyi");
  assert.equal(roadOfCard({ route: "", task_kind: "", tid: null }), null, "nothing judged it yet");
  const row = { RouteReason: "triage: task - weigh the quotes", TaskId: 8, TaskKind: "general" };
  assert.equal(roadOfCard({ route: row.RouteReason, tid: row.TaskId, task_kind: row.TaskKind }), roadOf(row));
});

// A report you set up, and an agent's own result, were judged by nobody - the row still says what
// it IS rather than going bare (the owner, 2026-09-07: "report should say report").
test("a row nothing triaged keeps the word for what it is", () => {
  assert.equal(roadOf({ Channel: "report", RouteReason: "a report you set up" }), null);
  assert.equal(roadOfCard({ route: "a report you set up", task_kind: "" }), null);
});

test("what is WAITING outranks what triage called the job", () => {
  // A drafted reply on a coding task wore "coding" beside its own envelope, because the pipe took
  // the road unconditionally - and the lane heading above the rail says "your task", which does not
  // say a reply is ready (the owner, 2026-09-14: "still says coding not reply waiting?"). The three
  // lanes that are ON the owner say their own word; every other row keeps the road, which is the
  // verdict the Timeline row and the Triage tab show.
  const view = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  assert.ok(view.includes('const loud = i.lane === "blocked" || i.lane === "approve" || i.lane === "time";'));
  assert.ok(view.includes(": loud ? meta.word : road ? road.label : meta.word;"),
    "what is waiting on you wins; everything else keeps the road");
  // loud is read by the tag, so it has to be computed before it
  assert.ok(view.indexOf('const loud = i.lane === "blocked"') < view.indexOf("const tag = i.settling"));
});

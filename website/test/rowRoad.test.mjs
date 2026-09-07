import test from "node:test";
import assert from "node:assert/strict";
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

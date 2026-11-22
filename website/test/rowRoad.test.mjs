import test from "node:test";
import assert from "node:assert/strict";

import { VERDICTS, roadOf, roadOfCard, verdictOf } from "../src/timelineState.js";

// The tag on a Timeline row is TRIAGE's word - the one the row's own Triage tab highlights - and
// nothing else (the owner, 2026-09-07: "the tag on the row should match what the triage shows
// nothing else"). It used to be the attention lane, which is about what is waiting NOW, so every
// finished row read "fyi" whatever triage had said: a question triage sent to Review wore the same
// word as a newsletter.
test("the row's word is the road triage took", () => {
  assert.equal(roadOf({ RouteReason: "triage: fyi - automated notice" }), "fyi");
  assert.equal(roadOf({ RouteReason: "triage: reply_only - Gail asks a simple question", TaskId: 404 }), "reply");
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


// ...and the rows triage never reached a verdict on. Your own standing rule turns a sender away
// without writing a `triage:` line, and a failed call writes no verdict at all - so roadOf had no
// word for either and the pill simply did not render. 94 policy-ignored rows in one week went out
// bare, plus every row the brain was down for (the owner, 2026-09-15: "on timeline items are
// missing tags??"). Read off `Decision`, the verdict itself, never off the reason prose.
test("a row triage never judged still says what happened to it", () => {
  assert.equal(verdictOf({ Decision: "ignore", MsgStatus: "ignored",
                           RouteReason: "policy 'not-a-task: cfg@bank.example': owner said not a task" }), "ignored");
  assert.equal(verdictOf({ MsgStatus: "error", Decision: "file",
                           RouteReason: "AI triage failed (azure_openai error 500) - unclassified" }), "error");
  assert.equal(verdictOf({ MsgStatus: "filed", Decision: "file", RouteReason: "triage: fyi - a newsletter" }), null,
    "triage reached a verdict here: the road word is the right one");
  assert.equal(verdictOf({}), null);
});

test("a failed triage outranks whatever thread it landed on", () => {
  // the follow-up that fails is often on a thread that already has a task, and roadOf would call
  // that "chat" - a road nothing chose for THIS message (PW-036/037)
  const row = { MsgStatus: "error", TaskId: 512, RouteReason: "AI triage failed (azure_openai error 500)" };
  assert.equal(verdictOf(row), "error");
  assert.equal(roadOf(row), "general", "roadOf is unchanged - the verdict is read first");
});

test("both verdicts carry a word and a hint", () => {
  for (const key of ["ignored", "error"]) {
    const v = VERDICTS.find((x) => x.key === key);
    assert.ok(v && v.label && v.hint, `${key} needs a word and a hint`);
  }
  assert.equal(VERDICTS.find((v) => v.key === "ignored").label, "ignored");
  assert.equal(VERDICTS.find((v) => v.key === "error").label, "couldn't sort this");
});

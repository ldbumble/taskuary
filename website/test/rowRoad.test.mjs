import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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

test("what is WAITING outranks what triage called the job", () => {
  // A drafted reply on a coding task wore "coding" beside its own envelope, because the pipe took
  // the road unconditionally - and the lane heading above the rail says "your task", which does not
  // say a reply is ready (the owner, 2026-09-14: "still says coding not reply waiting?"). The three
  // lanes that are ON the owner say their own word; every other row keeps the road, which is the
  // verdict the Timeline row and the Triage tab show.
  // The row says NOTHING but what it is now (the owner, 2026-09-16: "maybe just subject should be
  // there to clean it up"): the category heading above it carries the band, the dot carries the
  // source, and the only word left on a row is the lane where work has STOPPED until the owner
  // answers. So the road word is not outranked any more - it is gone from the row entirely.
  const view = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  assert.ok(view.includes('const loud = i.lane === "blocked" || i.lane === "approve";'));
  assert.doesNotMatch(view, /road \? road\.label : meta\.word/);
  // loud is read by the tag, so it has to be computed before it
  assert.ok(view.indexOf('const loud = i.lane === "blocked"') < view.indexOf("loud && !i.settling"));
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
  assert.equal(VERDICTS.find((v) => v.key === "error").label, "triage failed");
});

// the tag reads the verdict FIRST: an ignored row has no road, but an errored follow-up on a task
// does, and the road would win if the order were the other way round
test("the row's tag asks for the verdict before the road", () => {
  const view = readFileSync(new URL("../src/FeedView.jsx", import.meta.url), "utf8");
  const tag = view.slice(view.indexOf("export const tagMeta"), view.indexOf("const RoadTag"));
  assert.ok(tag.indexOf("VERDICTS.find") < tag.indexOf("ROADS.find"),
    "the verdict is read before the road, or a failed follow-up wears its thread's word");
});

// ONE WORD PER ROW, on both transports. The state mark was gated on `!r.Lane`, which is a transport
// detail rather than a question about words: /api/processing/all sets Lane on every row, so the mark
// never drew there even on a row the tag had no word for, while /api/feed (the "canonical grouping
// is still finishing" fallback, and any install whose processing reads are not active) sends none,
// so the mark drew BESIDE the word the row already had (the owner, 2026-09-15: "one word everywhere").
test("the state mark fills the gap, and never sits beside a word", () => {
  const view = readFileSync(new URL("../src/FeedView.jsx", import.meta.url), "utf8");
  assert.ok(view.includes("{!generic && !rowWord && !tagMeta(r) && <StateMark row={r} state={st} />}"),
    "the mark asks whether a word was produced, not which endpoint served the row");
  assert.ok(!/!generic && !r\.Lane && <StateMark/.test(view), "the transport-detail gate is gone");
  // ...and the lane word is computed once, so the tag and the gate cannot disagree about it
  assert.ok(view.includes('const rowWord = view === "unread" ? (r.Lane || rowLane(r)) : null;'));
  assert.ok(view.indexOf("const rowWord =") < view.indexOf("{rowWord ? <LaneTag"));
});

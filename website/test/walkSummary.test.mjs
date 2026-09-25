// The start of the walk groups the pile into who wants what (2026-09-23) - a grouping of lanes the pile
// already carries, so every lane lands in exactly one group and nothing is judged here.
import test from "node:test";
import assert from "node:assert/strict";
import { groupOf, stateOf, summarize, whoOf, GROUPS } from "../src/walkSummary.js";

const it = (lane, kind = "asked", extra = {}) => ({ key: `${lane}:${kind}:${Math.random()}`, lane, kind, who: "Erin Blake", title: "Q3 numbers", ...extra });

test("people, your own list, agents and the rest each land in their own group", () => {
  assert.equal(groupOf(it("approve", "review")), "people");         // a drafted reply: someone wants an answer
  assert.equal(groupOf(it("asked")), "people");
  assert.equal(groupOf(it("yours", "todo", { channel: "own" })), "you");   // a task you made yourself
  assert.equal(groupOf(it("yours", "todo", { channel: "email" })), "people");   // a person's ask, filed as a to-do
  assert.equal(groupOf(it("yours", "asked", { channel: "own" })), "you");
  assert.equal(groupOf(it("approve", "action")), "agents");          // an agent stopped before it acts
  assert.equal(groupOf(it("blocked", "agent")), "agents");
  assert.equal(groupOf(it("queued", "task")), "agents");
  assert.equal(groupOf(it("fyi", "fyi")), "read");
  assert.equal(groupOf(it("report", "report")), "read");
  assert.deepEqual(GROUPS.map((g) => g.key), ["people", "you", "agents", "read", "passed"]);
});

test("what you walked past with Next is its own group, as in the rail - never back under Agents waiting", () => {
  // the owner, 2026-09-24: "now it's gone from work but in the good evening list of tasks??"
  const passed = it("stopped", "agent", { surfaced: true });
  assert.equal(groupOf(passed), "passed");
  assert.equal(groupOf(it("stopped", "agent")), "agents");
  const s = summarize([passed, it("asked")]);
  assert.equal(s.lead, "2 things. 1 needs a word, 1 you passed.");
  assert.deepEqual(s.groups.map((g) => g.key), ["people", "passed"]);
});

test("the lead counts what is ready to approve first, and working rows are not waiting on anyone", () => {
  const s = summarize([it("approve", "review"), it("approve", "review"), it("asked"), it("yours", "todo", { channel: "own" }),
    it("fyi", "fyi"), it("working", "agent")]);
  assert.equal(s.n, 5);
  assert.equal(s.lead, "5 things. 2 are ready - you only approve, 1 needs a word, 1 is on your list, 1 you can skip.");
  assert.deepEqual(s.groups.map((g) => [g.key, g.rows.length]), [["people", 3], ["you", 1], ["read", 1]]);
  assert.equal(summarize([]).lead, "Nothing is waiting on you.");
  // a meeting is the day's strip above, never a row under People want
  assert.equal(summarize([it("time", "meeting"), it("asked")]).n, 1);
});

test("a drafted reply says it is ready, everything else says its lane's word", () => {
  assert.equal(stateOf(it("approve", "review"), "reply ready"), "draft ready");
  assert.equal(stateOf(it("approve", "action"), "reply ready"), "wants a yes");
  assert.equal(stateOf(it("asked"), "asked you"), "asked you");
});

test("a report's sender is its own title, so the row says Report instead of saying it twice", () => {
  assert.equal(whoOf({ kind: "report", lane: "report", who: "AP ageing over 30 days", title: "AP ageing over 30 days, weekly - 5 rows" }), "Report");
  assert.equal(whoOf({ kind: "asked", who: "Erin Blake", title: "Q3 numbers" }), "Erin Blake");
  assert.equal(whoOf({ kind: "agent", agent: "coder", title: "Reconcile the August GL export" }), "coder");
});

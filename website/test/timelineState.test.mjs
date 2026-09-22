import test from "node:test";
import assert from "node:assert/strict";
import { HOLD_TAG, STATES, stateOf, subline, triageSummary } from "../src/timelineState.js";

test("a question from the agent outranks everything the message once was", () => {
  assert.equal(stateOf({ TaskId: 7, Category: "coding", Working: "claude", AgentWaiting: true }), "waving");
  assert.equal(stateOf({ TaskId: 7, Category: "coding", Working: "claude" }), "working");
});

test("a newly arrived message has an explicit triaging state", () => {
  const row = { MessageId: 4, MsgStatus: "triaging", RouteReason: "" };
  assert.equal(stateOf(row), "triaging");
  assert.equal(STATES.triaging.mark, "spinner");
  assert.match(subline(row), /triage is deciding/);
});

test("a drafted reply is the headline even after the task closed", () => {
  assert.equal(stateOf({ TaskId: 7, TaskStatus: "done", ReviewStatus: "pending" }), "reply");
  assert.equal(stateOf({ TaskId: 7, TaskStatus: "done", ReviewStatus: "sent" }), "done");
});

test("a closed task never advertises a stale live session", () => {
  assert.equal(stateOf({ TaskId: 7, TaskStatus: "done", Working: "claude" }), "done");
});

test("a stranger's first message is its own state, not an absent one", () => {
  assert.equal(stateOf({ TaskId: 7, Category: "coding", TaskTags: "hold:new-sender" }), "held");
  assert.equal(stateOf({ TaskId: 7, Category: "coding", TaskTags: `repo:x,${HOLD_TAG}` }), "held");
  assert.equal(stateOf({ TaskId: 7, Category: "coding", TaskTags: "repo:x" }), "todo");
});

test("a note you left yourself is yours, and a report is not", () => {
  assert.equal(stateOf({ TaskId: 9, TaskKind: "note", Category: "todo" }), "mine");
  assert.equal(stateOf({ Category: "report", Channel: "report" }), "fyi");
  assert.equal(stateOf({ Category: "info" }), "fyi");
});

test("an open task with nobody on it is not an agent waving at you", () => {
  // NeedsYou only says nobody is moving this. It put the one loud mark on every open task.
  assert.equal(stateOf({ TaskId: 7, Category: "coding", NeedsYou: 1 }), "todo");
  assert.equal(stateOf({ TaskId: 7, Category: "coding", NeedsYou: 1, Working: "claude", AgentWaiting: true }), "waving");
});

test("only the two states that are genuinely on you are allowed to shout", () => {
  const loud = Object.entries(STATES).filter(([, s]) => s.loud).map(([k]) => k);
  assert.deepEqual(loud.sort(), ["reply", "waving"]);
});

test("the second line names who has it, never guesses", () => {
  assert.match(subline({ TaskId: 261, Working: "claude", AgentWaiting: true }), /TQ-0261 · claude asked you something/);
  assert.match(subline({ TaskId: 259, ReviewStatus: "pending" }), /TQ-0259 · a reply is drafted/);
  assert.equal(subline({ Category: "info", RouteReason: "triage: fyi - a colleague copied you" }),
               "fyi - a colleague copied you");
});

test("a thread whose last word is yours is waiting on them, not on you", () => {
  // an open task, and you replied (from anywhere) or Taskuary sent the reply: the ball is theirs
  const row = { TaskId: 7, Category: "coding", TheirTurn: 1, FromName: "Tess", Channel: "whatsapp" };
  assert.equal(stateOf(row), "theirs");
  assert.match(subline(row), /TQ-0007 · you replied · waiting on Tess/);
  assert.equal(STATES.theirs.loud, undefined);                        // never on you, so never loud
  // their next line arrives: the server clears TheirTurn and the row is work again
  assert.equal(stateOf({ TaskId: 7, Category: "coding", TheirTurn: 0 }), "todo");
  // a pending draft or a waving agent still outranks it - those ARE on you
  assert.equal(stateOf({ TaskId: 7, TheirTurn: 1, ReviewStatus: "pending" }), "reply");
  assert.equal(stateOf({ TaskId: 7, TheirTurn: 1, Working: "claude", AgentWaiting: true }), "waving");
  // and a closed task is simply done
  assert.equal(stateOf({ TaskId: 7, TheirTurn: 1, TaskStatus: "done" }), "done");
});

test("a message whose triage failed has an explicit error state with a retry hint", () => {
  // PW-036/037: failed triage is an error, never an fyi face
  const row = { MessageId: 9, MsgStatus: "error", RouteReason: "AI triage failed (model timed out) - retry available" };
  assert.equal(stateOf(row), "error");
  assert.match(STATES.error.word, /triage failed/i);
  assert.match(STATES.error.hint, /retry/i);
  assert.match(subline(row), /triage failed/i);
  // ...and it stays an error when the failed follow-up is linked to a task
  assert.equal(stateOf({ ...row, TaskId: 3, TaskStatus: "open" }), "error");
});

// THE TRIAGE STEP'S OWN WORDS. The row's chip and its Triage step read the same verdict off the
// same row, so they cannot disagree about it. The step used to consult only `roadOf`, which has no
// word for a standing rule turning a message away - so a message the owner's own policy had ignored
// reported itself as undecided and offered a choice that had already been made (the owner,
// 2026-09-15: "why does it say no classification - choose what happens below. it's ignore no
// choosing").
test("a message a standing rule turned away says so, and asks nothing", () => {
  const t = triageSummary({ Decision: "ignore", MsgStatus: "ignored",
    RouteReason: "policy 'not-a-task: noreply-securityapp@northwind.example': owner said not a task" });
  assert.equal(t.status, "ignored");
  assert.match(t.line, /not a task/);
  assert.equal(t.choose, false, "nothing is left to choose - the rule already chose");
});

test("a failed verdict asks, because nothing judged it", () => {
  const t = triageSummary({ MsgStatus: "error", RouteReason: "AI triage failed" });
  assert.equal(t.status, "triage failed");
  assert.equal(t.choose, true);
});

test("a road triage actually took is still reported as that road", () => {
  const t = triageSummary({ RouteReason: "triage: fyi - nothing to do here", Channel: "email" });
  assert.equal(t.status, "fyi");
  assert.equal(t.choose, false);
});

test("a message nothing has looked at yet still asks", () => {
  const t = triageSummary({ RouteReason: "", Channel: "email" });
  assert.equal(t.status, "not routed");
  assert.equal(t.choose, true);
});

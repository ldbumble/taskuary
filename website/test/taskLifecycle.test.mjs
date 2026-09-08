import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  agentPhase, focusStage, ownerControlsCompletion, pendingReplyReview, replyPhase, sentReplyReview, taskPhase, timelinePhases,
} from "../src/taskLifecycle.js";

test("task, agent and reply phases remain independent", () => {
  assert.equal(taskPhase("in_progress"), "in progress");
  assert.equal(agentPhase({ session: { alive: true, waiting: false } }), "working");
  assert.equal(replyPhase([{ Status: "pending", Kind: "draft" }]), "draft ready");
});

test("an action proposed after a reply never replaces the sender's draft", () => {
  const action = { ReviewId: 12, Status: "pending", Kind: "action", DraftText: '{"action":"write_playbook"}' };
  const reply = { ReviewId: 11, Status: "pending", Kind: "draft_reply", DraftText: "Answers to all eight items." };
  const reviews = [action, reply];
  assert.equal(pendingReplyReview(reviews), reply);
  assert.equal(replyPhase(reviews), "draft ready");
  assert.equal(replyPhase([action]), "not drafted");
});

test("an approved action is not mistaken for a sent reply", () => {
  const action = { ReviewId: 12, Status: "approved", Kind: "action" };
  const reply = { ReviewId: 11, Status: "sent", Kind: "draft_reply", DraftText: "Sent answer." };
  assert.equal(sentReplyReview([action, reply]), reply);
  assert.equal(replyPhase([action]), "not drafted");
  assert.equal(replyPhase([action, reply]), "sent");
});

test("owner completion policy is carried by the durable task tag", () => {
  assert.equal(ownerControlsCompletion({ Tags: "repo:x,stay:open" }), true);
  assert.equal(ownerControlsCompletion({ TaskTags: "coding" }), false);
});

test("timeline exposes task state beside current agent or reply attention", () => {
  assert.deepEqual(timelinePhases({ TaskStatus: "waiting", AgentWaiting: true }),
    { task: "waiting", agent: "needs you", reply: null });
  assert.deepEqual(timelinePhases({ TaskStatus: "done", ReviewStatus: "sent" }),
    { task: "done", agent: null, reply: "sent" });
});

test("terminal output never triggers whole-task HTTP refreshes", () => {
  const source = readFileSync(fileURLToPath(new URL("../src/TasksView.jsx", import.meta.url)), "utf8");
  assert.match(source, /pollWhileActive\(active, \(\) => loadDetail\(selected\), 3000\)/);
  assert.doesNotMatch(source, /onLive\([^\n]*run-tail[^\n]*loadDetail/);
  for (const file of ["ui.jsx", "FeedView.jsx", "BoardView.jsx", "WallView.jsx", "StudioView.jsx"]) {
    const view = readFileSync(fileURLToPath(new URL(`../src/${file}`, import.meta.url)), "utf8");
    assert.doesNotMatch(view, /onLive\([^\n]*run-tail/, `${file} must not turn terminal bytes into HTTP`);
  }
});

test("one stage is open: the last thing owed wins, and a closed task shows itself", () => {
  const draftReady = { kind: "coding", task: "open", agent: "result ready", reply: "draft ready", hasSender: true };
  assert.equal(focusStage(draftReady), "reply");                                    // sending it is what closes the task
  assert.equal(focusStage({ ...draftReady, agent: "needs you" }), "reply");
  assert.equal(focusStage({ kind: "reply", task: "open", agent: "not started", reply: "not drafted", hasSender: true }), "reply");
  assert.equal(focusStage({ kind: "coding", task: "open", agent: "not started", reply: "sent", hasSender: true }), "agent");
  assert.equal(focusStage({ kind: "general", task: "open", agent: "not started", reply: "not needed" }), "agent");
  assert.equal(focusStage({ kind: "task", task: "open", agent: "stopped", reply: "not drafted" }), "agent");
  assert.equal(focusStage({ kind: "task", task: "open", agent: "not started", reply: "not drafted" }), "task");
  assert.equal(focusStage({ kind: "reply", task: "open", agent: "not started", reply: "not drafted" }), "task");   // no sender to answer
  assert.equal(focusStage({ kind: "coding", task: "done", agent: "result ready", reply: "sent" }), "task");
  assert.equal(focusStage({}), "task");
});

test("the task page opens exactly one stage and lets you open the others by hand", () => {
  const source = readFileSync(fileURLToPath(new URL("../src/TasksView.jsx", import.meta.url)), "utf8");
  assert.match(source, /const stage = term\?\.alive \? "agent" : \(openStage \|\| focusStage\(/);
  assert.match(source, /setOpenStage\(null\)/);
  assert.match(source, /onToggle: stage === name \? null : \(\) => setOpenStage\(name\)/);   // the open one is not a control                                     // a new task recomputes its own focus
  for (const name of ["task", "agent", "reply"]) {
    assert.ok(source.includes(`{...stageProps("${name}")}`), `stage ${name} must fold and open by hand`);
    assert.ok(source.includes(`stage === "${name}" &&`), `stage ${name} body must be gated`);
  }
});

test("a general chat that has answered is agent state, not \"not started\"", () => {
  assert.equal(agentPhase({ conversation: true }), "in conversation");
  assert.equal(agentPhase({ conversation: true, report: { Body: "x" } }), "result ready");
  assert.equal(agentPhase({}), "not started");
  assert.equal(focusStage({ kind: "general", task: "open", agent: "in conversation", reply: "not drafted" }), "agent");
});

test("closing the task never hides behind a fold, and a finished chat can be closed out", () => {
  const source = readFileSync(fileURLToPath(new URL("../src/TasksView.jsx", import.meta.url)), "utf8");
  // the completion control rides on the heading, so it is there whether the card is open or folded
  assert.ok(source.includes('action={!["done", "dropped"].includes(t.Status) && stage !== "task"'), "the Task heading must carry the done control");
  assert.match(source, /const WorkflowHeading = \(\{ number, title, description, chip, tone, folded, onToggle, action \}\)/);
  // ...and a general conversation is wrappable once its provider session is gone (server.py/coder.py, 2026-09-07)
  assert.match(source, /const canWrap = !!term \|\| !!detail\?\.transcript \|\| hasGeneralHistory/);
  assert.match(source, /conversation: generalStarted/);
  assert.ok(source.includes("Save this conversation's result"), "the finished chat needs its own close-out");
  // interrupted work says so on the task page, not only in the list row
  assert.match(source, /interruptedTask && <Chip/);
});

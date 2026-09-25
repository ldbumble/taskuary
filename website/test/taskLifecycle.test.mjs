import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  agentPhase, focusStage, ownerControlsCompletion, pendingProposals, pendingReplyReview, replyPhase, sentReplyReview, taskPhase, timelinePhases,
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
  // the kind does not open the agent stage - having work in it does (2026-09-14)
  assert.equal(focusStage({ kind: "coding", task: "open", agent: "not started", reply: "sent", hasSender: true }), "task");
  assert.equal(focusStage({ kind: "general", task: "open", agent: "not started", reply: "not needed" }), "task");
  assert.equal(focusStage({ kind: "coding", task: "open", agent: "working", reply: "not drafted" }), "agent");
  assert.equal(focusStage({ kind: "general", task: "open", agent: "in conversation", reply: "not drafted" }), "agent");
  assert.equal(focusStage({ kind: "task", task: "open", agent: "stopped", reply: "not drafted" }), "agent");
  assert.equal(focusStage({ kind: "task", task: "open", agent: "not started", reply: "not drafted" }), "task");
  assert.equal(focusStage({ kind: "reply", task: "open", agent: "not started", reply: "not drafted" }), "task");   // no sender to answer
  assert.equal(focusStage({ kind: "coding", task: "done", agent: "result ready", reply: "sent" }), "task");
  assert.equal(focusStage({}), "task");
});

test("the task page opens exactly one stage and lets you open the others by hand", () => {
  const source = readFileSync(fileURLToPath(new URL("../src/TasksView.jsx", import.meta.url)), "utf8");
  // a session that fills the page IS the agent stage; stepping back from it (peek) opens the task
  // stage, the one that says what the task is and where it came from (2026-09-18)
  assert.match(source, /const stage = sessionView \? "agent" : \(openStage \|\| \(peek \? "task" : focusStage\(/);
  assert.match(source, /setOpenStage\(null\)/);
  assert.match(source, /onToggle: stage === name \? null : \(\) => setOpenStage\(name\)/);   // the open one is not a control                                     // a new task recomputes its own focus
  for (const name of ["agent", "reply"]) {
    assert.ok(source.includes(`{...stageProps("${name}")}`), `stage ${name} must fold and open by hand`);
    assert.ok(source.includes(`stage === "${name}" &&`), `stage ${name} body must be gated`);
  }
  // the Task card has no WorkflowHeading of its own since the page header became its heading
  // (2026-09-16): folded, it renders its own strip, and that strip is what opens it again
  assert.ok(source.includes(`stage !== "task" && (`), "the task card must render a folded strip");
  assert.ok(source.includes(`onClick={() => setOpenStage("task")}`), "stage task must open by hand");
  assert.ok(source.includes(`stage === "task" &&`), "stage task body must be gated");
});

test("a general chat that has answered is agent state, not \"not started\"", () => {
  assert.equal(agentPhase({ conversation: true }), "in conversation");
  assert.equal(agentPhase({ conversation: true, report: { Body: "x" } }), "result ready");
  assert.equal(agentPhase({}), "not started");
  assert.equal(focusStage({ kind: "general", task: "open", agent: "in conversation", reply: "not drafted" }), "agent");
});

test("closing the task never hides behind a fold, and a finished chat can be closed out", () => {
  const source = readFileSync(fileURLToPath(new URL("../src/TasksView.jsx", import.meta.url)), "utf8");
  // the completion control rides on the folded strip too, so it is there whether the card is open
  // or folded - the strip is the Task card's whole presence when the agent or reply has the focus
  const folded = source.slice(source.indexOf('stage !== "task" && ('), source.indexOf('{stage === "task" && <>'));
  assert.ok(folded.includes(">Mark done</Button>"), "the folded Task strip must carry the done control");
  assert.ok(folded.includes('finish("done")'), "and it must run the same completion road");
  assert.match(source, /const WorkflowHeading = \(\{ number, title, description, chip, tone, folded, onToggle, action \}\)/);
  // ...and a general conversation is wrappable once its provider session is gone (server.py/coder.py, 2026-09-07)
  assert.match(source, /const canWrap = !!term \|\| !!detail\?\.transcript \|\| hasGeneralHistory/);
  assert.match(source, /conversation: generalStarted/);
  assert.ok(source.includes("Save this conversation's result"), "the finished chat needs its own close-out");
  // interrupted work says so on the task page, not only in the list row
  assert.match(source, /interruptedTask && <Chip/);
});

test("the agent heading says what the agent is doing, not that a session exists", () => {
  // "② coder is working" sat beside its own chip reading "agent · needs you", because the title
  // asked only whether a pty was alive. The coder had been parked on a question for an hour
  // (the owner, 2026-09-11, TQ-0499: "is this the same bug?" - yes, the third surface of it).
  const view = readFileSync(fileURLToPath(new URL("../src/TasksView.jsx", import.meta.url)), "utf8");
  assert.doesNotMatch(view, /title=\{term\?\.alive \? `\$\{agentName\(t\)\} is working`/);
  assert.match(view, /agentState === "needs you" \? `\$\{agentName\(t\)\} needs you`/);
  // and the two states still come from one place: agentPhase already reads the session's own word
  assert.match(readFileSync(fileURLToPath(new URL("../src/taskLifecycle.js", import.meta.url)), "utf8"), /session\?\.alive\) return session\.waiting \? "needs you" : "working"/);
});

test("needs you is the one phase that wears the loud colour", () => {
  const ui = readFileSync(fileURLToPath(new URL("../src/ui.jsx", import.meta.url)), "utf8");
  // the palette has always said so - theme.jsx calls ALERT "the needs-you pill" - but the chip
  // used the pale tint, the same weight as four calmer phases (the owner, 2026-09-11)
  assert.match(ui, /needsYou: \{ bg: ALERT, fg: "#fffdfb", bd: ALERT \}/);
  assert.match(ui, /if \(value === "needs you"\) return LC\.needsYou;/);
  // ...and only that one: a draft waiting for a yes is not an agent blocked on you
  assert.match(ui, /if \(value === "draft ready" \|\| value === "approval needed" \|\| value === "ready"\) return LC\.you;/);
});

// A PROPOSAL IS A DECISION TOO. A playbook drafted after a coding job, or a setting proposed in
// chat, has no sender and still needs a yes - so the stage cannot be gated on there being someone
// to reply to, and the page cannot open folded over the only thing asking for you.
test("a proposal waiting on you opens the stage, sender or no sender", () => {
  const p = { kind: "coding", task: "open", agent: "not started", reply: "not drafted",
              hasSender: false, proposal: true };
  assert.equal(focusStage(p), "reply");
  assert.equal(focusStage({ ...p, proposal: false }), "task");
  assert.equal(focusStage({ ...p, task: "done" }), "reply", "a closed task still owes the yes");
});

test("proposals are not the reply, and the reply is not a proposal", () => {
  const reviews = [{ ReviewId: 3, Kind: "action", Status: "pending" },
                   { ReviewId: 2, Kind: "action", Status: "rejected" },
                   { ReviewId: 1, Kind: "draft", Status: "pending" }];
  assert.equal(pendingReplyReview(reviews).ReviewId, 1);
  assert.deepEqual(pendingProposals(reviews).map((r) => r.ReviewId), [3]);
  assert.deepEqual(pendingProposals([]), []);
});

// ONE EVENT SEEN TWICE. An agent parked because it PROPOSED something is not two things competing
// for the page: approving the proposal is what releases the agent. Opening the agent stage there
// shows a terminal sitting at a prompt with the thing that unblocks it folded away below.
// Parked on anything else - a question, a wall - the agent is what stopped, and it wins.
test("a waving agent outranks a proposal, unless the proposal is what it wants", () => {
  const base = { kind: "coding", task: "open", agent: "needs you", reply: "not drafted", proposal: true };
  assert.equal(focusStage({ ...base, agentSub: "asking" }), "agent");
  assert.equal(focusStage({ ...base, agentSub: "stalled" }), "agent");
  assert.equal(focusStage({ ...base, agentSub: "parked" }), "agent");
  assert.equal(focusStage({ ...base, agentSub: "approval" }), "reply");
  // and with nothing proposed, an approval-parked agent is still just a waving agent
  assert.equal(focusStage({ ...base, proposal: false, agentSub: "approval" }), "agent");
});

test("a drafted reply still outranks a waving agent, whatever it is parked on", () => {
  const base = { kind: "coding", task: "open", agent: "needs you", reply: "draft ready" };
  assert.equal(focusStage({ ...base, agentSub: "asking" }), "reply");
  assert.equal(focusStage({ ...base, agentSub: "approval" }), "reply");
});

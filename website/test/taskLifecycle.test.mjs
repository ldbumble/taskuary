import { taskSource } from "./taskSource.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  AGENT, agentPhase, focusStage, ownerControlsCompletion, sessionWord, wentOut, pendingProposals, pendingReplyReview, replyPhase, sentReplyReview, taskPhase, timelinePhases,
} from "../src/taskLifecycle.js";

test("task, agent and reply phases remain independent", () => {
  assert.equal(taskPhase("in_progress"), "in progress");
  assert.equal(agentPhase({ session: { alive: true, waiting: false } }), "agent working");
  assert.equal(replyPhase([{ Status: "pending", Kind: "draft" }]), "ready to send");
});

test("an action proposed after a reply never replaces the sender's draft", () => {
  const action = { ReviewId: 12, Status: "pending", Kind: "action", DraftText: '{"action":"write_playbook"}' };
  const reply = { ReviewId: 11, Status: "pending", Kind: "draft_reply", DraftText: "Answers to all eight items." };
  const reviews = [action, reply];
  assert.equal(pendingReplyReview(reviews), reply);
  assert.equal(replyPhase(reviews), "ready to send");
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
    { task: "waiting", agent: "agent waiting on you", reply: null });
  assert.deepEqual(timelinePhases({ TaskStatus: "done", ReviewStatus: "sent" }),
    { task: "done", agent: null, reply: "sent" });
});

test("terminal output never triggers whole-task HTTP refreshes", () => {
  const source = taskSource();
  assert.match(source, /pollWhileActive\(active, \(\) => loadDetail\(selected\), 3000\)/);
  assert.doesNotMatch(source, /onLive\([^\n]*run-tail[^\n]*loadDetail/);
  for (const file of ["ui.jsx", "FeedView.jsx", "BoardView.jsx", "WallView.jsx", "AssistantGame.jsx"]) {
    const view = readFileSync(fileURLToPath(new URL(`../src/${file}`, import.meta.url)), "utf8");
    assert.doesNotMatch(view, /onLive\([^\n]*run-tail/, `${file} must not turn terminal bytes into HTTP`);
  }
});

test("one stage is open: the last thing owed wins, and a closed task shows itself", () => {
  const draftReady = { kind: "coding", task: "open", agent: "stopped and saved", reply: "ready to send", hasSender: true };
  assert.equal(focusStage(draftReady), "reply");                                    // sending it is what closes the task
  assert.equal(focusStage({ ...draftReady, agent: "agent waiting on you" }), "reply");
  assert.equal(focusStage({ kind: "reply", task: "open", agent: "waiting to start", reply: "not drafted", hasSender: true }), "reply");
  // the kind does not open the agent stage - having work in it does (2026-09-14)
  assert.equal(focusStage({ kind: "coding", task: "open", agent: "waiting to start", reply: "sent", hasSender: true }), "task");
  assert.equal(focusStage({ kind: "general", task: "open", agent: "waiting to start", reply: "not needed" }), "task");
  assert.equal(focusStage({ kind: "coding", task: "open", agent: "agent working", reply: "not drafted" }), "agent");
  assert.equal(focusStage({ kind: "general", task: "open", agent: "stopped and saved", reply: "not drafted" }), "agent");
  assert.equal(focusStage({ kind: "task", task: "open", agent: "agent stopped", reply: "not drafted" }), "agent");
  assert.equal(focusStage({ kind: "task", task: "open", agent: "waiting to start", reply: "not drafted" }), "task");
  assert.equal(focusStage({ kind: "reply", task: "open", agent: "waiting to start", reply: "not drafted" }), "task");   // no sender to answer
  // finished: closed by you opens on Close out, where the close is shown (2026-10-19); closed by the agent itself, on its work
  assert.equal(focusStage({ kind: "coding", task: "done", agent: "stopped and saved", reply: "sent" }), "reply");
  assert.equal(focusStage({ kind: "coding", task: "done", agent: "stopped and saved", reply: "not needed" }), "reply");
  assert.equal(focusStage({ kind: "general", task: "done", agent: "waiting to start", record: true }), "reply");
  assert.equal(focusStage({ kind: "general", task: "done", agent: AGENT.finished, record: true }), "agent");
  assert.equal(focusStage({ kind: "task", task: "dropped", agent: "waiting to start" }), "task");
  assert.equal(focusStage({}), "task");
});

test("the task page opens exactly one stage and lets you open the others by hand", () => {
  const source = taskSource();
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
  assert.equal(agentPhase({ conversation: true }), "stopped and saved");
  assert.equal(agentPhase({ conversation: true, report: { Body: "x" } }), "stopped and saved");
  assert.equal(agentPhase({}), "waiting to start");
  assert.equal(focusStage({ kind: "general", task: "open", agent: "stopped and saved", reply: "not drafted" }), "agent");
});

test("closing the task never hides behind a fold, and a finished chat can be closed out", () => {
  const source = taskSource();
  // the completion control rides on the folded strip too, so it is there whether the card is open
  // or folded - the strip is the Task card's whole presence when the agent or reply has the focus
  const folded = source.slice(source.indexOf('stage !== "task" && ('), source.indexOf('{stage === "task" && <>'));
  assert.ok(folded.includes('labelOfRow("done")}</Button>'), "the folded Task strip must carry the done control");
  assert.ok(folded.includes("onClick={askFinish}"), "and it must run the same completion road (askFinish -> finish(\"done\"))");
  assert.match(source, /const WorkflowHeading = \(\{ number, title, description, chip, tone, folded, onToggle, action, tools \}\)/);
  // ...and a general conversation is wrappable once its provider session is gone (server.py/wrapup.py, 2026-09-07)
  assert.match(source, /const canWrap = !!term \|\| !!detail\?\.transcript \|\| hasGeneralHistory/);
  assert.match(source, /conversation: generalStarted/);
  // ...under the one name every ending wears, a chat's and a coding run's alike (2026-09-25)
  // ...ONE name for the write-up, live or ended (2026-10-02: "Save result" and "Stop and save" were one button twice)
  // ...but only while there is a session to stop: an ended one is closed out by Mark done (owner-approved, 2026-10-20)
  assert.ok(source.includes('onClick={wrapUp}>{labelOfRow("save-end")}</Button>'), "the live session's close-out");
  assert.ok(!source.includes(">Save result<") && !source.includes('label: "Save result"'));
  assert.ok(!source.includes("Save this conversation's result") && !source.includes("Save stopped run result"));
  // interrupted work says so on the task page, not only in the list row
  assert.match(source, /interruptedTask && <Chip/);
});

test("the agent heading says what the agent is doing, not that a session exists", () => {
  // "② <agent> is working" sat beside its own chip reading "agent · needs you", because the title
  // asked only whether a pty was alive. The agent had been parked on a question for an hour
  // (the owner, 2026-09-11, TQ-0499: "is this the same bug?" - yes, the third surface of it).
  const view = taskSource();
  assert.doesNotMatch(view, /title=\{term\?\.alive \? `\$\{agentName\(t\)\} is working`/);
  // ...and WHICH wait: asked, needs approval, stuck (T6, 2026-09-25)
  assert.match(view, /agentState === AGENT\.waiting \? says\(subState\(term\), agentName\(t\)\)/);
  // and the two states still come from one place: agentPhase already reads the session's own word
  assert.match(readFileSync(fileURLToPath(new URL("../src/taskLifecycle.js", import.meta.url)), "utf8"), /session\?\.alive\) return session\.waiting \? AGENT\.waiting : AGENT\.working/);
});

test("needs you is the one phase that wears the loud colour", () => {
  const ui = readFileSync(fileURLToPath(new URL("../src/ui.jsx", import.meta.url)), "utf8");
  // the palette has always said so - theme.jsx calls ALERT "the needs-you pill" - but the chip
  // used the pale tint, the same weight as four calmer phases (the owner, 2026-09-11)
  // ...solid, in On you's own sage since the five-colour palette (the owner, 2026-10-06: on you is not red) - still the
  // one SOLID phase among tinted ones
  assert.match(ui, /needsYou: \{ bg: "#5f7a5f", fg: "#fffdfb", bd: "#5f7a5f" \}/);
  assert.match(ui, /if \(value === AGENT\.waiting\) return LC\.needsYou;/);
  // ...and only that one: a draft waiting for a yes is not an agent blocked on you
  assert.match(ui, /if \(value === READY \|\| value === "approval needed" \|\| value === "ready"\) return LC\.you;/);
});

// A PROPOSAL IS A DECISION TOO. A playbook drafted after a coding job, or a setting proposed in
// chat, has no sender and still needs a yes - so the stage cannot be gated on there being someone
// to reply to, and the page cannot open folded over the only thing asking for you.
test("a proposal waiting on you opens the stage, sender or no sender", () => {
  const p = { kind: "coding", task: "open", agent: "waiting to start", reply: "not drafted",
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
  const base = { kind: "coding", task: "open", agent: "agent waiting on you", reply: "not drafted", proposal: true };
  assert.equal(focusStage({ ...base, agentSub: "asking" }), "agent");
  assert.equal(focusStage({ ...base, agentSub: "stalled" }), "agent");
  assert.equal(focusStage({ ...base, agentSub: "parked" }), "agent");
  assert.equal(focusStage({ ...base, agentSub: "approval" }), "reply");
  // and with nothing proposed, an approval-parked agent is still just a waving agent
  assert.equal(focusStage({ ...base, proposal: false, agentSub: "approval" }), "agent");
});

test("a drafted reply still outranks a waving agent, whatever it is parked on", () => {
  const base = { kind: "coding", task: "open", agent: "agent waiting on you", reply: "ready to send" };
  assert.equal(focusStage({ ...base, agentSub: "asking" }), "reply");
  assert.equal(focusStage({ ...base, agentSub: "approval" }), "reply");
});

test("a message after the agent's last session opens the task, not the old session", async () => {
  // the owner, 2026-10-12: a sender wrote back five days after the coding agent's session ended, and the page opened on that session
  const { focusStage, AGENT } = await import("../src/taskLifecycle.js");
  assert.equal(focusStage({ task: "open", agent: AGENT.saved, news: true }), "task");
  assert.equal(focusStage({ task: "open", agent: AGENT.saved }), "agent", "with no news the record still leads");
  assert.equal(focusStage({ task: "open", agent: AGENT.waiting, news: true }), "agent", "an agent asking now still wins");
});

// SEND KEEPS THE TASK, AND THE PAGE KEEPS CLOSE OUT (the owner, 2026-10-19): a reply sent on an open task whose agent finished or
// stopped opened the Agent work stage - the page went back to a finished agent's conversation after Send
test("a sent reply on an open task stays on Close out; only an agent working again takes the page", () => {
  for (const agent of [AGENT.finished, AGENT.saved, AGENT.stopped, null])
    assert.equal(focusStage({ kind: "general", task: "open", agent, reply: "sent", hasSender: true, record: true }), "reply", `agent ${agent}`);
  assert.equal(focusStage({ kind: "general", task: "open", agent: AGENT.working, reply: "sent", hasSender: true }), "agent");
  assert.equal(focusStage({ kind: "general", task: "open", agent: AGENT.waiting, reply: "sent", hasSender: true }), "agent");
});

// ...and every close-out, not only a reply: a pull request merged, an issue closed (approved actions), an email the task owed
test("after a merge, a closed issue or an owed email went out, the page stays on Close out", () => {
  for (const r of [{ Kind: "action", Status: "approved" }, { Kind: "slot", Status: "sent" }, { Kind: "draft", Status: "edited" }])
    assert.equal(wentOut([r]), true, JSON.stringify(r));
  assert.equal(wentOut([{ Kind: "action", Status: "pending" }, { Kind: "draft", Status: "no_reply" }]), false);
  for (const agent of [AGENT.finished, AGENT.saved, null])
    assert.equal(focusStage({ kind: "coding", task: "open", agent, reply: "not drafted", out: true, record: true }), "reply", `agent ${agent}`);
  assert.equal(focusStage({ kind: "coding", task: "open", agent: AGENT.working, reply: "not drafted", out: true }), "agent");
  assert.equal(focusStage({ kind: "coding", task: "done", agent: AGENT.finished, reply: "not drafted", out: true, record: true }), "reply");
});

test("a session's new word is a change the task page takes, and the same word is not (G7)", () => {
  const working = { sid: "a1", alive: true, waiting: false, state: null, tail: ["Reading the export job."] };
  const asking = { ...working, waiting: true, state: "asking", line: "coding asked you: Keep the rows?", request: { request_id: "r1" } };
  assert.notEqual(sessionWord(working), sessionWord(asking));
  assert.equal(sessionWord(working), sessionWord({ ...working, tail: ["more output"], idle: 3 }));   // output alone is not a new word
  assert.equal(agentPhase({ session: asking }), AGENT.waiting);
  assert.equal(sessionWord(null), "");
});

// STOP AND SAVE ONLY WHILE THERE IS SOMETHING TO STOP (owner-approved, 2026-10-20): a stopped run offered it (G7), and so did one
// that failed, finished or was cut off by a restart - every one of its doors on the task page is the live session's now
test("an ended session offers no Stop and save anywhere on the task page - only the live session's row and controls", () => {
  const page = readFileSync(fileURLToPath(new URL("../src/TaskPage.jsx", import.meta.url)), "utf8");
  assert.doesNotMatch(page, /canSave|endedByStop/, "no second road to the write-up for a session that has ended");
  assert.equal((page.match(/\{ id: "save-end"/g) || []).length, 1, "one row verb");
  const live = page.indexOf("...(liveSession ? ["), uses = [...page.matchAll(/\[stopSave\]/g)].map((m) => m.index);
  assert.ok(uses.length === 2 && uses.every((at) => at > live && at - live < 900), "...and it is the live session's");
  assert.equal((page.match(/>\{labelOfRow\("save-end"\)\}<\/Button>/g) || []).length, 1, "one button: the live controls'");
});

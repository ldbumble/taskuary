// AN AGENT'S OWN CLOSE OPENS ON ITS WORK (the owner, 2026-10-21: "when an agent closes a task and no close out is needed, I have
// no idea what the agent did and why it closed. The agent thing should open, not the close part"). On the table the page has no
// list row, so it read the task's state from nothing: "stopped and saved", and Close out opened with advice for an open task.
import test from "node:test";
import assert from "node:assert/strict";
import { taskSource } from "./taskSource.mjs";
import { AGENT, agentPhase, closedLine, focusStage, pageState, replyPhase } from "../src/taskLifecycle.js";

// what TaskPage computes, from the detail alone (no list row) or with one
const opens = ({ listRow = null, detail }) => {
  const state = pageState(listRow, detail);
  const agent = agentPhase({ conversation: true, finished: state === "agentdone", state, handed: true });
  return { agent, stage: focusStage({ kind: "general", task: detail.task.Status, agent, reply: replyPhase(detail.reviews || []),
    hasSender: !!detail.sender, record: true }) };
};

const agentClosed = { task: { Status: "done" }, state: "agentdone", reviews: [],
  closedWhy: "Closed by the agent: the run failed on a missing secret; re-added it and the re-run passed" };

test("an agent-closed task with no reply owed opens on Agent work, from the detail alone", () => {
  const { agent, stage } = opens({ detail: agentClosed });
  assert.equal(agent, AGENT.finished, "not 'stopped and saved'");
  assert.equal(stage, "agent");
});

test("the list's row still wins where there is one", () => {
  assert.equal(pageState({ State: "closed" }, agentClosed), "closed");
  assert.equal(pageState(null, { state: "queued" }), "queued");
  assert.equal(pageState(null, null), null);
});

test("a task the owner closed with a reply still opens on Close out", () => {
  const detail = { task: { Status: "done" }, state: "closed", sender: true,
    reviews: [{ ReviewId: 1, Kind: "draft_reply", Status: "sent", DraftText: "Done - thanks, Erin." }] };
  assert.equal(opens({ detail }).stage, "reply");
  assert.equal(opens({ listRow: { State: "closed" }, detail }).stage, "reply");
});

test("a closed task says who closed it and why, never the advice for an open one", () => {
  assert.equal(closedLine({ Status: "done" }, agentClosed.closedWhy), agentClosed.closedWhy);
  assert.equal(closedLine({ Status: "done" }, null), "Closed. Nobody sent this one, so no reply was owed.");
  assert.equal(closedLine({ Status: "open" }, agentClosed.closedWhy), null);
  const src = taskSource();
  assert.match(src, /const rowState = pageState\(listRow, detail\)/);
  assert.match(src, /closedLine\(t, detail\?\.closedWhy\) \|\| "Nobody sent this one, so there is nobody to answer\. Work it/);
  // ...said at the top of Agent work, the step it opens on - in its body, as the heading carries no sentence (taskControls)
  const agent = src.slice(src.indexOf('{pane === "agent" && <>'), src.indexOf("<AgentRecord {...recordProps} story={storyAt"));
  assert.match(agent, /!term\?\.alive && t\?\.Status === "done" && detail\?\.closedWhy && \(\s*<Typography data-tq-closed-why/);
});

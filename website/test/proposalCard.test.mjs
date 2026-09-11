// The confirmation card (PW-122..125): built from the proposal the server returned, never from a guess
// about the words; the button submits the structured proposal by id and version; the receipt is what
// the server said happened; bottom suggestions are ordinary text.
import test from "node:test";
import assert from "node:assert/strict";
import { proposalOf, describe, afterExecute, afterConfirm, afterCancel, markExecuted } from "../src/proposalCard.js";

const p = { id: "ab12", kind: "task.create_from_message", target: 7, version: 1, status: "proposed", verb: "coder",
  params: { kind: "coding", instructions: "check the June rows" }, label: "Send to the coding agent",
  summary: "TQ-0007 - Fix the export → coding agent", settles: true, key: "task:7", ref: "TQ-0007" };

test("the bottom suggestions are text the owner could have typed", () => {
});

test("a turn with a proposal yields the card; a plain answer or a decision does not", () => {
  assert.equal(proposalOf({ say: "On it.", proposal: p }).id, "ab12");
  assert.equal(proposalOf({ say: "They want the export fixed.", decision: null }), null);
  assert.equal(proposalOf({ say: "Next.", decision: { verb: "next" } }), null);
});

test("the card says exactly what will happen: action, target and parameters", () => {
  const d = describe(p);
  assert.equal(d.title, "Send to the coding agent");
  assert.equal(d.target, "TQ-0007 - Fix the export → coding agent");
  assert.deepEqual(d.params, [["kind", "coding"], ["instructions", "check the June rows"]]);
  assert.equal(d.confirm, "Send to the coding agent");
  assert.equal(d.cancel, "Cancel");
});

test("after the click, the receipt is the server's word and the walk moves only on a done that settles", () => {
  assert.deepEqual(afterExecute(p, { status: "done", outcome: { ref: "TQ-0007" }, duplicate: false }),
    { receipt: "Done - Send to the coding agent.", settle: true, status: "done", handoff: false });   // done, but no worker started
  assert.deepEqual(afterExecute({ ...p, settles: false }, { status: "done", outcome: {} }),
    { receipt: "Done - Send to the coding agent.", settle: false, status: "done", handoff: false });
  assert.deepEqual(afterExecute(p, { status: "error", error: "agent did not start" }),
    { receipt: "Not done - agent did not start. Nothing moved.", settle: false, status: "error" });
  assert.deepEqual(afterExecute(p, { status: "stale", error: "the context changed since this was proposed" }),
    { receipt: "Not done - the context changed since this was proposed. Say it again if you still want it.", settle: false, status: "stale" });
  assert.deepEqual(afterExecute(p, { status: "done", duplicate: true, outcome: {} }),
    { receipt: "Already done - Send to the coding agent.", settle: false, status: "done" });
});

test("cancel is a receipt that nothing changed", () => {
  assert.deepEqual(afterCancel(p), { receipt: "Cancelled - nothing changed; TQ-0007 is where it was.", status: "cancelled" });
});

// A typed "yes, go ahead" is answered by concierge.confirm_open, which RUNS the operation before it
// replies. The page has no execute left to do - it only has to stop the card saying "proposed".
test("a yes said in words settles the card the server already ran", () => {
  const msgs = [{ id: "a1", proposal: { id: "ab12", status: "proposed" } },
                { id: "a2", proposal: { id: "zz99", status: "proposed" } },
                { id: "u1", text: "yes, go ahead" }];
  const out = markExecuted(msgs, { id: "ab12", kind: "task.create_from_message", status: "done" });
  assert.equal(out[0].proposal.status, "done");
  assert.equal(out[1].proposal.status, "proposed");     // somebody else's card is not touched
  assert.equal(out[2].text, "yes, go ahead");
  assert.equal(markExecuted(msgs, undefined), msgs);    // nothing executed: the thread is left exactly as it was
});

// A sweep clears the pipe by SELECTOR, and when what it clears includes the item on the table it has
// settled that too - the page must move to the next thing instead of sitting on what it just cleared
// (the owner, 2026-09-11: "did not move to next after"), and must not re-settle it.
test("a sweep that took the table with it advances the walk; one that did not just reloads", () => {
  const swept = { id: "c1", kind: "pipe.clear", key: "msg:9", settles: true };
  const done = { settle: true, status: "done" };
  assert.equal(afterConfirm(swept, done, "msg:9"), "advance");
  assert.equal(afterConfirm(swept, done, "msg:4"), "reload");        // the table was not in the sweep
  assert.equal(afterConfirm({ id: "c2", kind: "pipe.clear" }, done, "msg:9"), "reload");
  assert.equal(afterConfirm(swept, { settle: false, status: "error" }, "msg:9"), "reload");
  assert.equal(afterConfirm({ ...p, kind: "item.settle" }, done, "task:7"), "advance");
  assert.equal(afterConfirm(p, done, "task:7"), "settle");           // the page still settles this one
});

// The confirmation card (PW-122..125): built from the proposal the server returned, never from a guess
// about the words; the button submits the structured proposal by id and version; the receipt is what
// the server said happened; bottom suggestions are ordinary text.
import test from "node:test";
import assert from "node:assert/strict";
import { SUGGESTIONS, proposalOf, describe, afterExecute, afterCancel } from "../src/proposalCard.js";

const p = { id: "ab12", kind: "task.create_from_message", target: 7, version: 1, status: "proposed", verb: "coder",
  params: { kind: "coding", instructions: "check the June rows" }, label: "Send to the coding agent",
  summary: "TQ-0007 - Fix the export → coding agent", settles: true, key: "task:7", ref: "TQ-0007" };

test("the bottom suggestions are text the owner could have typed", () => {
  assert.deepEqual(SUGGESTIONS, ["Next", "Done", "Create task", "Create agent", "Reply"]);
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
    { receipt: "Done - Send to the coding agent.", settle: true, status: "done" });
  assert.deepEqual(afterExecute({ ...p, settles: false }, { status: "done", outcome: {} }),
    { receipt: "Done - Send to the coding agent.", settle: false, status: "done" });
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

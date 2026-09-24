// The confirmation card (PW-122..125): built from the proposal the server returned, never from a guess
// about the words; the button submits the structured proposal by id and version; the receipt is what
// the server said happened; bottom suggestions are ordinary text.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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
  assert.deepEqual(d.params, [["instructions", "check the June rows"]]);   // kind: the button already says it
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

test("the server's receipt is the one drawn - never a second, shorter Done beside it", () => {
  const said = "Done - Put it on my list · TQ-0009. TQ-0009 - \"Call Erin\" is on your list; no agent was started.";
  assert.equal(afterExecute(p, { status: "done", outcome: {}, receipt: said }).receipt, said);
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
// settled that too - so the page puts the table down and OFFERS Next, rather than walking on by itself
// (the owner, 2026-09-11: "it doesn't have to move on but should show button next") and rather than
// leaving the cleared report sitting there as Current ("did not move to next after").
test("a sweep that took the table with it offers Next; one that did not just reloads", () => {
  const swept = { id: "c1", kind: "pipe.clear", key: "msg:9", settles: true };
  const done = { settle: true, status: "done" };
  assert.equal(afterConfirm(swept, done, "msg:9"), "offer");
  assert.equal(afterConfirm(swept, done, "msg:4"), "reload");        // the table was not in the sweep
  assert.equal(afterConfirm({ id: "c2", kind: "pipe.clear" }, done, "msg:9"), "reload");
  assert.equal(afterConfirm(swept, { settle: false, status: "error" }, "msg:9"), "reload");
  assert.equal(afterConfirm({ ...p, kind: "item.settle" }, done, "task:7"), "advance");
  assert.equal(afterConfirm(p, done, "task:7"), "settle");           // the page still settles this one
});

// The Next button itself: the receipt row carries chips, and a sweep that took the table puts one there.
test("the receipt after a sweep carries Next, and the page puts the table down without walking on", () => {
  const view = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  assert.match(view, /const chips = step === "offer" \? \[\{ verb: "next", label: "Next" \}\] : \[\];/);
  assert.match(view, /role: "receipt", text: out\.receipt, tid: p\.tid \|\| res\?\.outcome\?\.taskId, ref: p\.ref \|\| res\?\.outcome\?\.ref, chips/);
  assert.match(view, /\{last && !!chipsOf\(m\)\.length && \(/);       // the receipt row renders them
  assert.match(view, /const clearTable = \(\) => \{/);                 // putting the table down is not advancing
  assert.doesNotMatch(view, /if \(step === "offer"\) advance\(\)/);
});

test("a hand-off in words is a job, not a form: the brief once, and a coding job names its repository", () => {
  const brief = "Look into issue 920 on the fan app and make sure the screening job is scheduled and working.";
  const cut = describe({ kind: "task.create_from_text", label: "Start a coding agent on it",
    params: { kind: "coding", text: brief, title: "Look into issue 920 on the fan app and make sure the", repo: "northwind/ledger" } });
  assert.equal(cut.target, brief);                                   // the title was the brief cut short: said once
  assert.equal(cut.detail, "");
  assert.deepEqual(cut.params, [["repository", "northwind/ledger"]]); // no "text:" / "title:" rows
  const own = describe({ kind: "task.create_from_text", label: "Start a regular agent on it",
    params: { kind: "general", text: brief, title: "Fan app screening" } });
  assert.equal(own.target, "Fan app screening");
  assert.equal(own.detail, brief);
  assert.equal(own.params.length, 1);                                // no checkout for a non-coding agent...
  assert.equal(own.params[0][0], "agent");                           // ...but it names who takes it, or that nobody clearly does
  const named = describe({ kind: "task.create_from_text", label: "Start the researcher on it",
    params: { kind: "general", text: brief, title: "Fan app screening", profile: "researcher" } });
  assert.deepEqual(named.params, [["agent", "researcher"]]);
  const marked = describe({ kind: "task.create_from_text", label: "Start a coding agent on it",
    params: { kind: "coding", text: brief, title: "Look into issue 920 on the fan app and make sure the screening…" } });
  assert.equal(marked.detail, "");                                  // "…" marks a cut, it does not make a new title
  const guessed = describe({ kind: "task.create_from_text", label: "Start a coding agent on it", clear: false,
    params: { kind: "coding", text: brief, repo: "northwind/ledger" } });
  assert.match(guessed.params[0][1], /^northwind\/ledger - a best guess/);
  const unsure = describe({ kind: "task.create_from_text", label: "Start a coding agent on it", params: { kind: "coding", text: brief } });
  assert.match(unsure.params[0][1], /you pick it/);
});

test("a coding hand-off nobody named a checkout for asks for one on the card", async () => {
  const { pickingRepo } = await import("../src/proposalCard.js");
  const base = { kind: "task.create_from_text", params: { kind: "coding", text: "tidy the dashboard" }, repo_choices: ["northwind/ledger", "northwind/portal"] };
  assert.equal(pickingRepo({ ...base, clear: false }), true);
  assert.equal(pickingRepo({ ...base, clear: true }), false);                      // named: it starts, nothing to pick
  assert.equal(pickingRepo({ ...base, clear: false, params: { kind: "general", text: "x" } }), false);
  assert.equal(pickingRepo({ ...base, clear: false, repo_choices: [] }), false);
});

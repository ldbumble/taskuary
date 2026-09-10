import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { sendBlockLine, draftState, replyEnvelope, replySendFailure } from "../src/sendState.js";

test("reply envelopes preserve exact saved To and CC and distinguish other delivery kinds", () => {
  const env = { kind: "reply", to: ["a@example.test", "b@example.test"], cc: ["c@example.test"], delivery: "unknown" };
  assert.deepEqual(replyEnvelope({ Deliver: JSON.stringify(env) }), env);
  assert.deepEqual(replyEnvelope({ Deliver: env }), env);
  for (const Deliver of [undefined, "{", "null", '{"kind":"outbound","to":["hidden@example.test"]}']) {
    assert.equal(replyEnvelope({ Deliver }), null);
  }
});

test("a delivery timeout is unknown, while an explicit failed send remains a failure", () => {
  assert.deepEqual(replySendFailure({ send_error: "provider timeout", delivery: "unknown" }),
    { message: "provider timeout", unknown: true });
  assert.deepEqual(replySendFailure({ send_error: "rejected", delivery: "failed" }),
    { message: "rejected", unknown: false });
  assert.equal(replySendFailure({ sent: { id: "sent-once" } }), null);
});

// PW-044/PW-046: a draft is always there to read and edit; whether it can be SENT is a separate
// fact the server states, and every surface shows the same reason instead of a send button.

test("a blocked channel yields the server's reason, an open one yields nothing", () => {
  assert.equal(sendBlockLine({ CanSend: false, Channel: "teams", SendBlock: "replies are off for teams (Settings → Replies)" }),
    "Cannot send from here: replies are off for teams (Settings → Replies). The draft stays here to copy or edit.");
  assert.equal(sendBlockLine({ CanSend: false, Channel: "github", SendBlock: "" }), "Cannot send from here: GitHub replies are off (GitHub card). The draft stays here to copy or edit.");
  assert.equal(sendBlockLine({ CanSend: true, Channel: "email", SendBlock: "" }), "");
  assert.equal(sendBlockLine(null), "");
});

test("the draft state names a failed draft with its reason and offers the retry", () => {
  assert.deepEqual(draftState({ HasDraft: 0, DraftError: "no AI connector is set up to write replies" }),
    { state: "failed", line: "Draft failed: no AI connector is set up to write replies. Retry drafting or write the answer yourself.", retry: true });
  assert.deepEqual(draftState({ HasDraft: 0, DraftError: "" }), { state: "undrafted", line: "No draft yet — draft it with AI or write the answer.", retry: true });
  assert.deepEqual(draftState({ HasDraft: 1, DraftError: "" }), { state: "drafted", line: "", retry: false });
  assert.deepEqual(draftState({ DraftText: "hello", DraftError: null }), { state: "drafted", line: "", retry: false });
});

test("the review, task-panel and assistant surfaces are wired to the shared send state", () => {
  for (const f of ["FeedView.jsx", "assistantCards.jsx"]) {
    const src = readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
    assert.match(src, /sendBlockLine\(/, `${f} shows the shared reason`);
    assert.match(src, /draftState\(/, `${f} shows the shared draft state`);
  }
});

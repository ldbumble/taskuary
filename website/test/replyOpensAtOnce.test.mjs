// A REPLY IS THE TASK'S AGENT'S (the owner, 2026-11-27: "side model should never work in agent canvas"): Reply, Redraft and the Assistant's
// "reply to X" were a one-shot writer drafting behind the card (/api/reviews/{rid}/draft). The press is now one call - his ask to the
// task's agent (server.open_reply) - and nothing is drafted behind it.
import test from "node:test";
import assert from "node:assert/strict";


import { withSignature } from "../src/signature.js";
import * as replyDraft from "../src/replyDraft.js";
import { askReply, boxText } from "../src/replyDraft.js";


const fakeApi = () => {
  const calls = [];
  return { calls, post: async (url, body) => { calls.push([url, body]); return { data: { taskId: 7, ref: "TQ-0007", asked: true, receipt: { status: "done", text: "Asked the agent on TQ-0007." } } }; } };
};

test("Reply and Redraft are one call: his ask to the task's agent, nothing drafted behind it", async () => {
  const api = fakeApi();
  const out = await askReply(api, 9, "say yes");
  assert.equal(out.taskId, 7);
  await askReply(api, 9, null, "redraft", 77);
  assert.deepEqual(api.calls, [["/api/messages/9/reply", { instruction: "say yes", verb: "reply" }],
                               ["/api/messages/9/reply", { instruction: null, verb: "redraft", line: 77 }]], "never a /draft behind it");
  for (const gone of ["openReply", "draftBehind", "draftJob", "useDraftJob", "rewriteReceipt"]) assert.equal(replyDraft[gone], undefined, gone);
});

test("the box holds the owner's words over the draft, and the signature under an empty one", () => {
  const sign = "Alex Doyle\nNorthwind";
  assert.equal(boxText({ text: null, draft: "", signature: sign }), withSignature("", sign), "nothing drafted: the signature to write over");
  assert.equal(boxText({ text: null, draft: "Yes.", signature: sign }), withSignature("Yes.", sign));
  assert.equal(boxText({ text: "my own words", draft: "Yes.", signature: sign }), "my own words", "the owner's edit is never wiped");
});

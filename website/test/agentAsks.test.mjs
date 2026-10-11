// The Task page draws what a live session is asking - text, options, the hold - and answers on the Assistant's roads (B11).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { asksOf, answerCall, allPicked } from "../src/agentAsks.js";

const one = { alive: true, held: true, questions: [],
  request: { request_id: "q:abc0123456:1", kind: "input_needed", text: "Which branch should I base this on?", choices: ["main", "release/2026-10"] } };
const group = { alive: true, held: true, request: { request_id: "q:abc0123456:2", kind: "input_needed", text: "Which color?", choices: ["red", "blue"] },
  questions: [{ request_id: "q:abc0123456:1", text: "Which branch?", choices: ["main", "dev"] },
              { request_id: "q:abc0123456:2", text: "Which color?", choices: ["red", "blue"] }] };

test("a held question shows its text and options, and says it is held", () => {
  const a = asksOf(one);
  assert.equal(a.held, true);
  assert.deepEqual(a.questions, [{ request_id: "q:abc0123456:1", text: "Which branch should I base this on?", choices: ["main", "release/2026-10"] }]);
});

test("nothing asked, a stall, or a dead session draws nothing", () => {
  assert.equal(asksOf({ alive: true, request: null }), null);
  assert.equal(asksOf({ alive: true, request: { request_id: "s1", kind: "stalled", text: "rate limit" } }), null);
  assert.equal(asksOf({ ...one, alive: false }), null);
});

test("one question posts to /worker/answer, a group to /worker/answers - and only whole", () => {
  assert.deepEqual(answerCall(7, asksOf(one), { "q:abc0123456:1": "main" }),
    ["/api/tasks/7/worker/answer", { request_id: "q:abc0123456:1", text: "main" }]);
  const g = asksOf(group);
  assert.equal(g.questions.length, 2, "every question of the ask, in order");
  assert.equal(allPicked(g, { "q:abc0123456:1": "main" }), false);
  const picks = { "q:abc0123456:1": "main", "q:abc0123456:2": "blue" };
  assert.equal(allPicked(g, picks), true);
  assert.deepEqual(answerCall(7, g, picks), ["/api/tasks/7/worker/answers", { answers: picks }]);
});

test("the Task page draws it under the pane, with a way to let the terminal have it", () => {
  const page = fs.readFileSync(path.join(process.cwd(), "src", "TaskPage.jsx"), "utf8");
  const card = fs.readFileSync(path.join(process.cwd(), "src", "AgentAsks.jsx"), "utf8");
  assert.match(page, /<AgentAsks taskId=\{selected\}/);
  assert.match(card, /worker\/release/);
});

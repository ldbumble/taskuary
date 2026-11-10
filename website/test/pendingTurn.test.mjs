// THE AGENT'S TURN IS ON SCREEN THE MOMENT IT IS ASKED FOR (the owner, 2026-11-09): an answer sent on the server's road drew nothing under the
// owner's line until the request came back, then a headless "Working on this…" that went and came back as the turn.
import assert from "node:assert/strict";
import test from "node:test";

import { live, pendingTurn, sentNow, settled } from "../src/pendingTurn.js";

const you = (id, text) => ({ id, role: "user", content: [{ type: "text", text }] });
const agent = (id, text, o = {}) => ({ id, role: "assistant", content: [{ type: "text", text }], ...o });
// what the chat draws at its end: the thread's turns, then the pane's own agent row while one is due
const drawn = (thread, o) => [...thread.map((m) => m.id), ...(pendingTurn(thread, o) ? ["pending"] : [])];

test("a send draws the agent's turn at once, before any request has come back", () => {
  const thread = [you("u1", "Who signs off the AP cutover?"), agent("a1", "Gail Moreno, by Thursday. Shall I ask her?")];
  const sent = sentNow(thread, 1000);                       // kept by the press itself, before the answer goes
  assert.deepEqual(drawn(thread, { sent }), ["u1", "a1", "pending"]);
  assert.equal(sent.at, 1000);
});

test("a server read without the turn keeps the agent's row; one with the live turn takes its place", () => {
  const before = [you("u1", "Who signs off the AP cutover?"), agent("a1", "Gail Moreno. Shall I ask her?")];
  const sent = sentNow(before);
  // the server has the owner's line, not the turn yet: the row stays, under it
  const kept = [...before, you("u2", "Yes, ask her")];
  assert.deepEqual(drawn(kept, { sent }), ["u1", "a1", "u2", "pending"]);
  assert.equal(settled(kept, sent), false);
  // ...the session's turn arrives (a `live-` row from its trace): the row is gone and the turn is at the same spot
  const turn = [...kept, agent("live-g9-3", "")];
  assert.ok(live(turn.at(-1)));
  assert.deepEqual(drawn(turn, { sent, busy: true }), ["u1", "a1", "u2", "live-g9-3"]);
  assert.equal(drawn(kept, { sent }).indexOf("pending"), drawn(turn, { sent, busy: true }).indexOf("live-g9-3"));
  // ...and the answer lets the press go
  assert.equal(settled([...kept, agent("a2", "Asked her.")], sent), true);
  assert.deepEqual(drawn([...kept, agent("a2", "Asked her.")], { sent }), ["u1", "a1", "u2", "a2"]);
});

test("an agent at work that the thread does not draw yet is a turn with its head, never a bare line", () => {
  const thread = [you("u1", "Pull the September overtime"), agent("a1", "Done - by site, attached.")];
  assert.deepEqual(drawn(thread, { busy: true }), ["u1", "a1", "pending"]);
  assert.deepEqual(drawn(thread, {}), ["u1", "a1"]);
  // this pane's own stream draws its own running turn
  assert.deepEqual(drawn([...thread, you("u2", "and October?"), agent("r1", "", { status: { type: "running" } })], { busy: true }),
    ["u1", "a1", "u2", "r1"]);
});

// THE CHAT'S OWN SEND (CI, 2026-11-10: "5115: no running head: nothing"; the frame-by-frame watch, CPU slowed as a runner is: his line drawn at
// 89 ms and nothing under it until 186-331 ms): the runtime draws his line a beat before its run begins, and no press of the pane's kept `sent`
// - the line just drawn, with nothing after it, is the turn owed, its head under it in the same paint
test("a line of his the thread has just drawn, with nothing after it, draws the agent's turn under it at once", () => {
  const now = Date.now(), line = { ...you("u2", "look at the south office first"), createdAt: new Date(now - 50) };
  assert.equal(pendingTurn([you("u1", "hi"), agent("a1", "Hi."), line], { now }), true);
  // ...not a brief, not a press, not a line from long ago that nothing answered
  assert.equal(pendingTurn([{ ...line, metadata: { custom: { brief: true } } }], { now }), false);
  assert.equal(pendingTurn([{ ...line, metadata: { custom: { press: true } } }], { now }), false);
  assert.equal(pendingTurn([{ ...line, createdAt: new Date(now - 3600000) }], { now }), false);
  assert.equal(pendingTurn([line, agent("a2", "On it.")], { now }), false, "an answer after it is the turn");
});

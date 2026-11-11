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
  // ...a turn the server says began (its `turnStarted`), one the thread does not draw yet
  assert.deepEqual(drawn(thread, { busy: true, began: Date.now() }), ["u1", "a1", "pending"]);
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

// ONE FACT FOR "THIS TURN IS OVER" (the recorded rewrite walk, 2026-11-10, frame 00353: as the turn filed its answer a second "AGENT · ran 5s ×"
// head stood for a beat under the new card - the server's working flag, read a poll later, still said busy): the answer filed is the turn over,
// unless the turn at work began after it
test("an answer filed at or after the turn at work began ends it, whatever a late working flag says", () => {
  const began = Date.parse("2026-11-10T10:00:00Z"), answer = agent("a2", "Rewrote it short.", { createdAt: new Date(began + 5000) });
  assert.equal(pendingTurn([you("u1", "make it shorter"), answer], { busy: true, began }), false);
  // ...a turn that began after the answer (a mail woke the agent): drawn from its start
  assert.equal(pendingTurn([you("u1", "make it shorter"), answer], { busy: true, began: began + 9000 }), true);
  assert.equal(pendingTurn([you("u1", "make it shorter"), answer], { busy: true }), false, "no start said: a working flag alone is no new turn");
});

// ...AND A START THE SERVER HELD IS NO TURN (the recorded walk, 2026-11-10): his line on a stranger's task whose AI could not start - the hold
// said under it with its Trust - stood with a running "AGENT · ran 6s" head over the hold for a minute, the fresh line's bridge
test("a line whose start was held has no running head under it, its hold said instead", () => {
  const thread = [you("u1", "make it shorter and attach the sheet")];
  thread[0].createdAt = new Date().toISOString();
  assert.deepEqual(drawn(thread, {}), ["u1", "pending"], "a fresh line bridges the beat before its run begins");
  assert.deepEqual(drawn(thread, { held: true }), ["u1"], "held: nothing is running");
  assert.deepEqual(drawn(thread, { held: true, busy: true }), ["u1", "pending"], "...until a run is at work after all");
});

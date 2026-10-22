// ONE STATUS, TWO PLACES (the redesign, owner-approved 2026-10-21): the task header's pill and the rail row's icon wear the same mark and
// word for one task, read from lanes.json through the rail's own rowMeta - so they cannot disagree.
import test from "node:test";
import assert from "node:assert/strict";
import { ANIM, BADGE, railStatus, stateStatus, statusLabel, taskStatus } from "../src/railStatus.js";
import { LANE_META, rowMeta } from "../src/funnelPile.js";

test("the header's status is exactly the rail row's mark and word, for every lane", () => {
  for (const lane of Object.keys(LANE_META)) {
    const item = { lane, kind: "task" }, st = taskStatus({ rail: item }), m = rowMeta(item);
    assert.deepEqual([st.mark, st.word], [m.mark, m.word], lane);
    assert.deepEqual(railStatus(item), st, `${lane}: the rail's icon and the header read one status`);
  }
  // a kind over its lane, and a refused send over both - as the rail says them
  assert.equal(railStatus({ lane: "report", kind: "agentdone" }).word, "agent finished");
  assert.equal(railStatus({ lane: "approve", kind: "review", not_sent: true }).word, "didn't send");
});

test("an agent at work spins; only the hand waves", () => {
  const working = railStatus({ lane: "working", kind: "task" });
  assert.equal(working.spins, true); assert.equal(working.anim, "ring"); assert.equal(working.badge, "");
  assert.equal(railStatus({ lane: "working", settling: true }).spins, false, "a row still settling never spins");
  assert.equal(railStatus({ lane: "blocked" }).anim, "wave", "👋 waves");
  for (const lane of ["approve", "saved", "stopped", "theirs", "queued"]) assert.equal(railStatus({ lane }).anim, null, `${lane} holds still`);
  assert.deepEqual(Object.keys(ANIM).sort(), ["asked", "blocked"]);
});

test("the live session's word leads, then the rail's row, then the server's state", () => {
  assert.equal(taskStatus({ live: { alive: true, waiting: false }, rail: { lane: "approve" } }).key, "working");
  assert.equal(taskStatus({ live: { alive: true, waiting: true }, rail: { lane: "working" } }).key, "blocked");
  assert.equal(taskStatus({ rail: { lane: "approve", kind: "review" }, state: "yours" }).word, "ready to send");
  // no rail row (the Tasks tab, or a closed task): the server's own state, in the same words
  assert.equal(taskStatus({ state: "agentdone" }).word, "agent finished");
  assert.equal(taskStatus({ state: "closed" }).word, "done");
  assert.equal(taskStatus({ state: "theirs" }).word, "waiting on them");
  assert.equal(taskStatus({ state: "working" }).spins, true);
  assert.equal(taskStatus({}), null);
  // a closed task pulled onto the table by a link wears no stale lane: the server says it is done
  assert.equal(taskStatus({ rail: { lane: "fyi" }, state: "closed", closed: true }).word, "done");
  assert.equal(taskStatus({ rail: { lane: "fyi" }, state: "agentdone", closed: true }).word, "agent finished");
  assert.equal(stateStatus("nonsense"), null);
});

test("the state is readable without colour or motion: its words are the icon's label", () => {
  assert.equal(statusLabel(railStatus({ lane: "approve" })), "ready to send");
  assert.equal(statusLabel(railStatus({ lane: "working" }), "Coding agent"), "Coding agent is working on this");
  assert.equal(statusLabel(railStatus({ lane: "working" })), "an agent is working on this");
  assert.equal(statusLabel(null), "");
});

// TOO MANY EMOJIS (the owner, 2026-10-22): a badge only where the move is the owner's - the hand of somebody waiting on you and the flag
// of a reply ready to send. Every other state is the plain logo, its words the icon's label; the header pill keeps every lane's mark.
test("only waiting on you and ready to send wear a badge; every other state is the plain logo, said in words", () => {
  assert.deepEqual(BADGE, { blocked: "👋", asked: "👋", approve: "🏁" });
  for (const [lane, badge] of Object.entries({ blocked: "👋", asked: "👋", approve: "🏁" })) assert.equal(railStatus({ lane }).badge, badge, lane);
  for (const lane of ["yours", "queued", "saved", "stopped", "time", "theirs", "broken", "unjudged", "forgotten"]) {
    const st = railStatus({ lane });
    assert.equal(st.badge, "", `${lane}: the plain logo`); assert.equal(st.spins, false);
    assert.equal(statusLabel(st), st.word, `${lane}: its words are its label`);
    assert.ok(st.mark, `${lane}: the header pill still has its mark`);
  }
  assert.equal(railStatus({ lane: "approve", not_sent: true }).badge, "", "a refused send is said in words, not a flag");
  assert.equal(railStatus({ lane: "working" }).badge, "");
  // every lane, kind and state: a badge is only ever the hand or the flag
  for (const key of [...Object.keys(LANE_META)]) assert.ok(["", "👋", "🏁"].includes(stateStatus(key).badge), key);
});

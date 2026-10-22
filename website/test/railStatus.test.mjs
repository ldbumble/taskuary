// ONE STATUS, TWO PLACES (the redesign, owner-approved 2026-10-21): the task header's pill and the rail row's icon wear the same mark and
// word for one task, read from lanes.json through the rail's own rowMeta - so they cannot disagree.
import test from "node:test";
import assert from "node:assert/strict";
import { MOVES, RING, RINGS, railStatus, stateStatus, statusLabel, taskStatus } from "../src/railStatus.js";
import { KIND_META, LANE_META, STATE_META, rowMeta } from "../src/funnelPile.js";

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

test("the ring round the logo says every state, one shape each - and the logo itself never changes", () => {
  const working = railStatus({ lane: "working", kind: "task" });
  assert.equal(working.spins, true); assert.equal(working.ring, "spin");
  assert.equal(railStatus({ lane: "working", settling: true }).ring, "none", "a row still settling never spins");
  const rings = { blocked: "breathe", asked: "breathe", approve: "full", saved: "half", stopped: "half", broken: "broken", unjudged: "broken",
    queued: "dots", theirs: "faint", yours: "none" };
  for (const [lane, ring] of Object.entries(rings)) assert.equal(railStatus({ lane }).ring, ring, lane);
  assert.equal(railStatus({ lane: "approve", not_sent: true }).ring, "broken", "didn't send is a broken ring");
  assert.equal(stateStatus("held").ring, "faint");
  for (const k of ["closed", "agentdone", "answered"]) assert.equal(stateStatus(k).ring, "none", `${k}: done wears no ring`);
  // the states the owner reads apart wear different shapes: failed is never stopped, waiting to start is never waiting on them
  const shape = (lane) => railStatus({ lane }).ring;
  assert.equal(new Set(["working", "blocked", "approve", "saved", "broken", "queued", "theirs", "yours"].map(shape)).size, 8);
  // every lane, kind and state lands on a known ring, and only an agent at work spins
  for (const key of [...Object.keys(LANE_META), ...Object.keys(KIND_META), ...Object.keys(STATE_META)]) {
    const st = stateStatus(key);
    assert.ok(RINGS.includes(st.ring), `${key} wears ${st.ring}`);
    assert.equal(st.ring === "spin", key === "working", `${key}: only an agent at work spins`);
    assert.equal("look" in st, false, `${key}: the logo has no look of its own`);
  }
  for (const v of Object.values(RING)) assert.ok(RINGS.includes(v));
  assert.deepEqual(MOVES, ["spin", "breathe", "dots"]);
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

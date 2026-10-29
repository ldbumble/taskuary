// ONE STATUS, TWO PLACES (the redesign, owner-approved 2026-10-21): the task header's pill and the rail row's icon wear the same mark and
// word for one task, read from lanes.json through the rail's own rowMeta - so they cannot disagree.
import test from "node:test";
import assert from "node:assert/strict";
import { ANIM, BADGE, agentGone, railStatus, rowWhy, stateStatus, statusLabel, taskStatus } from "../src/railStatus.js";
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
  // ...but a parked agent the server read as its drafted reply waiting (taskstate `approve`) is that, as the Board and the rail say (2026-10-29)
  assert.equal(taskStatus({ live: { alive: true, waiting: true }, state: "approve" }).word, "ready to send");
  assert.equal(taskStatus({ live: { alive: true, waiting: false }, state: "approve" }).key, "working");
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

test("a reply owed with no draft yet wears no flag and no 'ready to send' - the rail row and the header alike, until the draft lands", () => {
  const owed = { lane: "approve", kind: "review", draft: false, channel: "email" };
  const row = railStatus(owed), pill = taskStatus({ rail: owed });
  assert.equal(row.key, "owed"); assert.equal(row.word, "reply owed"); assert.equal(row.badge, ""); assert.deepEqual(pill, row);
  assert.equal(railStatus(owed, true).key, "owed", "no draft is no draft to copy either");
  // ...the draft lands: the flag and the words come back
  assert.equal(railStatus({ ...owed, draft: true }).word, "ready to send"); assert.equal(railStatus({ ...owed, draft: true }).badge, "🏁");
  // the task's own read is newer than the rail's: its draft lifts "reply owed", its missing draft puts it there - Tasks tab included
  assert.equal(taskStatus({ rail: owed, owed: false }).key, "approve");
  assert.equal(taskStatus({ rail: { ...owed, draft: true }, owed: true }).key, "owed");
  assert.equal(taskStatus({ state: "approve", owed: true }).word, "reply owed");
  // an agent's proposed action, a refused send and a row with no draft field keep their own words
  assert.equal(taskStatus({ rail: { lane: "approve", kind: "action" }, owed: true }).key, "approve");
  assert.equal(railStatus({ ...owed, not_sent: true }).key, "not_sent");
  assert.equal(railStatus({ lane: "approve", kind: "review" }).key, "approve");
});

test("a draft its channel cannot send wears no flag and no 'ready to send' - on the rail row and the header pill alike", () => {
  const teams = { lane: "approve", kind: "review", channel: "teams" };
  const row = railStatus(teams, true), pill = taskStatus({ rail: teams, cantSend: true });
  assert.equal(row.key, "unsendable"); assert.equal(row.badge, ""); assert.notEqual(row.word, "ready to send");
  assert.deepEqual(pill, row, "the header says what the rail says");
  // ...with no rail row (the Tasks tab) the server's approve state reads the same
  assert.equal(taskStatus({ state: "approve", cantSend: true }).key, "unsendable");
  // a channel that sends, an agent's proposed action, and a refused send keep their own words
  assert.equal(railStatus(teams, false).word, "ready to send");
  assert.equal(railStatus({ lane: "approve", kind: "action" }, true).key, "approve");
  assert.equal(taskStatus({ rail: { lane: "approve", kind: "action" }, cantSend: true }).key, "approve");
  assert.equal(railStatus({ ...teams, not_sent: true }, true).key, "not_sent");
});

// AN AGENT LANE IS A CLAIM ABOUT A LIVE SESSION (the owner, 2026-10-23: "this shows agent working but it's not working"): the agent had
// finished, its pty was closed and its reply waited in Close out, while a rail built minutes earlier still said "agent working" - on the
// row and on the header pill that reads it - beside the Result that said it had finished. A task read newer than the rail takes it back.
test("a newer read of the task takes back the rail's agent lane - on the row, its line and the header pill alike", () => {
  const row = { lane: "working", kind: "agent", tid: 7, why: "An agent is working on this; nothing needs your input yet" };
  for (const [state, word] of [["approve", "ready to send"], ["agentdone", "agent finished"], ["stopped", "agent stopped"], ["saved", "stopped and saved"]]) {
    const page = { live: false, state };
    const st = railStatus(row, false, page), pill = taskStatus({ rail: row, state, page });
    assert.equal(st.word, word, state); assert.equal(st.spins, false, `${state}: nothing spins`);
    assert.deepEqual(pill, st, `${state}: the header pill says what the row says`);
    assert.doesNotMatch(rowWhy(row, page), /is working on this/, `${state}: the row's line goes with its lane`);
  }
  // a reply its channel cannot send is a draft to copy here too
  assert.equal(railStatus(row, true, { live: false, state: "approve" }).key, "unsendable");
  // ...and an agent waving on a stale rail is taken back the same way
  assert.equal(railStatus({ lane: "blocked", tid: 7 }, false, { live: false, state: "agentdone" }).word, "agent finished");
  // the rail stands when no newer read speaks, when that read still has the agent live, or itself names an agent state
  assert.equal(railStatus(row, false, null).spins, true);
  assert.equal(railStatus(row, false, { live: true, state: "agentdone" }).spins, true);
  assert.equal(railStatus(row, false, { live: false, state: "working" }).spins, true);
  assert.equal(railStatus(row, false, { live: false, state: null }).spins, true);
  assert.equal(rowWhy(row, null), row.why);
  // ...and only an agent lane is ever taken back: a reply ready to send is the rail's own word whatever the read says
  assert.equal(agentGone({ lane: "approve" }, { live: false, state: "agentdone" }), false);
  assert.equal(railStatus({ lane: "approve", kind: "review" }, false, { live: false, state: "agentdone" }).word, "ready to send");
  // a live session on the page still leads everything
  assert.equal(taskStatus({ live: { alive: true, waiting: false }, rail: row, page: { live: false, state: "approve" } }).key, "working");
});

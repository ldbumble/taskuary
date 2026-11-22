import { taskSource } from "./taskSource.mjs";
// A session can be started from anywhere - the Assistant's "send to the coding agent", the Board,
// a second window - and the task page has to notice. TQ-0500 (2026-09-11): the Board showed a live
// coding session while the task page said "agent - not started" and offered to start one, which
// would have put a second agent in the same checkout.
//
// The page could not learn it, by construction. findTerm only ran when the SELECTION changed; the
// detail poll only ran once something was already known to be live; and the one live subscription
// refreshed the LIST alone - which is why the row on the left said "agent working" in the very same
// screenshot as the panel on the right saying "not started".
import test from "node:test";
import assert from "node:assert/strict";


import { agentPhase } from "../src/taskLifecycle.js";

const src = taskSource();

test("a live session anywhere means the agent stage is working, not 'not started'", () => {
  assert.equal(agentPhase({ session: { alive: true } }), "agent working");
  assert.equal(agentPhase({ session: { alive: true, waiting: true } }), "agent waiting on you");
  // the shape the task detail actually carries (server: hub_term.for_task)
  assert.equal(agentPhase({ session: { sid: "c0df3a87bfa1", alive: true, agent: "coding" } }), "agent working");
  assert.equal(agentPhase({}), "waiting to start");
});


test("a session that has ENDED is not adopted over the one findTerm kept", () => {
  // findTerm deliberately keeps a dead session: its scrollback is what Done and Pause read, and
  // for_task only ever returns a live one, so adopting unconditionally would drop the transcript.
  const guard = /const live = detail\?\.session;\s*\n\s*if \(!live\?\.alive \|\|/;
  assert.match(src, guard, "the adoption must be gated on alive");
  assert.equal(agentPhase({ session: { alive: false }, transcript: "scrollback" }), "agent stopped");
});

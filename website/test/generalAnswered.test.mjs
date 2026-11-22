// A general agent's chat session stays open after it answers, and the page asked only whether the session existed - so the heading
// said "researcher is working · agent working" under its finished answer (the owner, 2026-10-15). Answered and open is waiting on you.
import test from "node:test";
import assert from "node:assert/strict";
import { AGENT, agentPhase, generalAnswered } from "../src/taskLifecycle.js";

test("a general session that is open but not busy has answered; a busy one is working; a coding session is never 'answered'", () => {
  assert.equal(generalAnswered(true, { alive: true, busy: false }), true);
  assert.equal(generalAnswered(true, { alive: true, busy: true }), false);
  assert.equal(generalAnswered(false, { alive: true, busy: false }), false);
  // ...and one the server says is not waiting - opened for a turn that has not taken yet - has not answered (email walk 2026-10-29)
  assert.equal(generalAnswered(true, { alive: true, busy: false, waiting: false }), false);
  assert.equal(generalAnswered(true, { alive: true, busy: false, waiting: true }), true);
  assert.equal(agentPhase({ session: { alive: true, waiting: generalAnswered(true, { alive: true, busy: false }) } }), AGENT.waiting);
});

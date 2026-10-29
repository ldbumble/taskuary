// A general agent's chat session stays open after it answers, and the page asked only whether the session existed - so the heading
// said "researcher is working · agent working" under its finished answer (the owner, 2026-10-15). Answered and open is waiting on you.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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

test("the heading says it answered", () => {
  assert.match(readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8"), /answered \? `\$\{agentName\(t\)\} answered`/);
});

test("a task read with no live session lets go of the answered chat session the page held", () => {
  // the header kept "agent waiting on you" over an agent that had closed itself, until a reload (email walk 2026-10-29)
  assert.match(readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8"),
    /if \(detail\?\.session\?\.alive \|\| detail\?\.task\?\.TaskId !== selected\) return;\s*if \(term\?\.alive && term\.mode === "assistant" && term\.taskId === selected && term\.busy === false && !pressedHere\) setTerm\(null\);/);
});

test("the chat's poll hands the page the session it read, so the turn's end reaches the heading", () => {
  // the page held the session the turn STARTED with (busy) - the poll refreshed only the chat, and the heading said "is working"
  // under the finished answer for as long as you looked (2026-10-15)
  const gw = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(gw, /setData\(fresh\);[\s\S]{0,240}onSession\?\.\(fresh\.session \|\| null\);/);
});

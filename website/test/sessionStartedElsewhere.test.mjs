// A session can be started from anywhere - the Assistant's "send to the coding agent", the Board,
// a second window - and the task page has to notice. TQ-0500 (2026-09-11): the Board showed a live
// coder session while the task page said "agent - not started" and offered to start one, which
// would have put a second agent in the same checkout.
//
// The page could not learn it, by construction. findTerm only ran when the SELECTION changed; the
// detail poll only ran once something was already known to be live; and the one live subscription
// refreshed the LIST alone - which is why the row on the left said "agent working" in the very same
// screenshot as the panel on the right saying "not started".
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { agentPhase } from "../src/taskLifecycle.js";

const src = readFileSync(fileURLToPath(new URL("../src/TasksView.jsx", import.meta.url)), "utf8");

test("a live session anywhere means the agent stage is working, not 'not started'", () => {
  assert.equal(agentPhase({ session: { alive: true } }), "working");
  assert.equal(agentPhase({ session: { alive: true, waiting: true } }), "needs you");
  // the shape the task detail actually carries (server: hub_term.for_task)
  assert.equal(agentPhase({ session: { sid: "c0df3a87bfa1", alive: true, agent: "coder" } }), "working");
  assert.equal(agentPhase({}), "not started");
});

test("the open task is reloaded on task-changed, not just the list", () => {
  const sub = /onLive\("task-changed",([\s\S]*?)\);\n/.exec(src);
  assert.ok(sub, "TasksView must subscribe to task-changed");
  assert.match(sub[1], /loadDetail\(/,
    "refreshing only the list is how the row said 'agent working' beside a panel saying 'not started'");
});

test("the session the detail already carries is adopted", () => {
  assert.match(src, /const live = detail\?\.session;/,
    "the detail carries the live session - sessionAlive is read off it - so the page must take it");
  assert.match(src, /live\?\.alive && live\.sid !== term\?\.sid/,
    "adopt only a LIVE session, and only when it is one we do not already hold");
});

test("a session that has ENDED is not adopted over the one findTerm kept", () => {
  // findTerm deliberately keeps a dead session: its scrollback is what Done and Pause read, and
  // for_task only ever returns a live one, so adopting unconditionally would drop the transcript.
  const guard = /const live = detail\?\.session;\s*\n\s*if \(live\?\.alive/;
  assert.match(src, guard, "the adoption must be gated on alive");
  assert.equal(agentPhase({ session: { alive: false }, transcript: "scrollback" }), "stopped");
});

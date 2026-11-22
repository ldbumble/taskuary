// Consistent worker startup across the surfaces that start one (PW-209..214).
//
// The All-detail row hid Send to agent for fyi/reply rows that chat cards happily dispatch; the
// task page's "Use
// non-coding agent" only re-labelled the task's kind and left a workspace mount to start work.
// Every surface now reads one dispatch outcome and shows what actually happened.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { outcomeOf } from "../src/dispatchOutcome.js";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");

test("a dispatch answer is read as started, existing, needs_repo or assistant - never a decision as a start", () => {
  assert.equal(outcomeOf({ dispatch: "needs_repo", taskId: 3, agent: "coding" }).state, "needs_repo");
  assert.equal(outcomeOf({ dispatch: "session", started: true, accepted: true, agent: "coding", ref: "TQ-0003" }).state, "started");
  assert.match(outcomeOf({ dispatch: "session", started: true, accepted: true, agent: "coding", ref: "TQ-0003" }).text, /coding is on it/);
  assert.match(outcomeOf({ dispatch: "session", started: true, accepted: false, agent: "coding", ref: "TQ-0003" }).text, /opening|typing/i);
  assert.equal(outcomeOf({ dispatch: "session", started: false, existing: true, agent: "coding", ref: "TQ-0003" }).state, "existing");
  assert.match(outcomeOf({ dispatch: "session", started: false, existing: true, agent: "coding", ref: "TQ-0003" }).text, /already/);
  assert.equal(outcomeOf({ dispatch: "assistant", started: true, agent: "cli:claude", ref: "TQ-0004" }).state, "started");
  // ...and a general agent is "on it", never "in a live session" - a coding session's words (stress test 2026-11-03)
  assert.equal(outcomeOf({ dispatch: "assistant", started: true, agent: "Claude Code", ref: "TQ-0004" }).text, "Claude Code is on it - TQ-0004");
  assert.match(outcomeOf({ dispatch: "session", started: true, accepted: true, agent: "coding" }).text, /in a live session$/);
  // an older server without the flags: a session payload is a start, a needs_repo is not
  assert.equal(outcomeOf({ dispatch: "session", session: { sid: "s" } }).state, "started");
  assert.equal(outcomeOf({ dispatch: "needs_repo" }).state, "needs_repo");
});

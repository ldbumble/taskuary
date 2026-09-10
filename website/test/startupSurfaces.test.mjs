// Consistent worker startup across the surfaces that start one (PW-209..214).
//
// The All-detail row hid Send to agent for fyi/reply rows that chat cards happily dispatch; the
// timeline's SendToAgent read a needs_repo decision as a live start; the task page's "Use
// non-coding agent" only re-labelled the task's kind and left a workspace mount to start work.
// Every surface now reads one dispatch outcome and shows what actually happened.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { outcomeOf } from "../src/dispatchOutcome.js";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");

test("a dispatch answer is read as started, existing, needs_repo or assistant - never a decision as a start", () => {
  assert.equal(outcomeOf({ dispatch: "needs_repo", taskId: 3, agent: "coder" }).state, "needs_repo");
  assert.equal(outcomeOf({ dispatch: "session", started: true, accepted: true, agent: "coder", ref: "TQ-0003" }).state, "started");
  assert.match(outcomeOf({ dispatch: "session", started: true, accepted: true, agent: "coder", ref: "TQ-0003" }).text, /coder is on it/);
  assert.match(outcomeOf({ dispatch: "session", started: true, accepted: false, agent: "coder", ref: "TQ-0003" }).text, /opening|typing/i);
  assert.equal(outcomeOf({ dispatch: "session", started: false, existing: true, agent: "coder", ref: "TQ-0003" }).state, "existing");
  assert.match(outcomeOf({ dispatch: "session", started: false, existing: true, agent: "coder", ref: "TQ-0003" }).text, /already/);
  assert.equal(outcomeOf({ dispatch: "assistant", started: true, agent: "cli:claude", ref: "TQ-0004" }).state, "started");
  // an older server without the flags: a session payload is a start, a needs_repo is not
  assert.equal(outcomeOf({ dispatch: "session", session: { sid: "s" } }).state, "started");
  assert.equal(outcomeOf({ dispatch: "needs_repo" }).state, "needs_repo");
});

test("the timeline's SendToAgent handles the repository decision instead of calling it a start", () => {
  const ui = src("ui.jsx");
  const handoff = ui.slice(ui.indexOf("export const SendToAgent"), ui.indexOf("export const TASK_STATES"));
  assert.match(handoff, /outcomeOf\(data\)/);
  assert.match(handoff, /needs_repo/);
  assert.match(handoff, /RepoPicker/);
  assert.doesNotMatch(handoff, /setSent\(data\);\s*setPrompt\(""\);\s*onOpenTask/);   // the old unconditional "it started"
});

test("All detail offers Send to agent for fyi and reply rows too, like the chat cards do", () => {
  const feed = src("FeedView.jsx");
  const tray = feed.slice(feed.indexOf("{onIt && sel.TaskId && <TellAgentButton"), feed.indexOf("<TalkItThrough messageId"));
  assert.doesNotMatch(tray, /!codeless/);
  assert.match(tray, /<SendToAgent messageId=\{sel\.MessageId\}/);
});

test("the task page's non-coding start goes through the shared dispatch, whatever the task's kind was", () => {
  const tasks = src("TasksView.jsx");
  const fn = tasks.slice(tasks.indexOf("const startGeneralAgent = async"), tasks.indexOf("useEffect(() => { if (!liveCodingSession)"));
  assert.match(fn, /api\.post\(`\/api\/tasks\/\$\{id\}\/dispatch`, \{ kind: "general" \}\)/);
  assert.doesNotMatch(fn, /api\.patch\(`\/api\/tasks\/\$\{id\}`, \{ Kind: "general"/);
  assert.match(fn, /outcomeOf\(data\)/);
});

// "New task → Ask the assistant" opened the chat on the right task and left it EMPTY: the
// prompt the owner typed never got asked (TQ-0275 "Whats up", 2026-08-31).
//
// Two faults, both of them about a task's data belonging to that task:
//   1. `detail` is not cleared when the selection changes, so for one render it still holds the
//      PREVIOUS task - and the decision was made from that one's Kind, Summary and repo.
//   2. the seed was cleared "whenever the selection changes", which is the very event that
//      produced it: set and wiped in the same commit, gone before the chat mounted.
import assert from "node:assert/strict";
import test from "node:test";
import { autostartPlan, isGeneralKind, opensOnRegular } from "../src/autostart.js";

const detailOf = (TaskId, Kind, Summary = "") => ({ task: { TaskId, Kind, Summary } });

test("a general task starts nothing here - the chat asks its own question", () => {
  const plan = autostartPlan({ autostart: { taskId: 7 }, selected: 7,
    detail: detailOf(7, "general", "Whats up"), hasSession: false });
  assert.equal(plan.do, "chat");
  assert.equal(plan.seed, undefined);       // handing it through here is what lost it, twice
});

test("the PREVIOUS task's detail decides nothing", () => {
  // the exact window that broke it: selection has moved to 7, detail still holds 6
  const plan = autostartPlan({ autostart: { taskId: 7 }, selected: 7,
    detail: detailOf(6, "general", "the last task's prompt"), hasSession: false });
  assert.equal(plan.do, "wait");
});



test("a coding task starts a terminal, and never a second one", () => {
  const args = { autostart: { taskId: 7 }, selected: 7, detail: detailOf(7, "coding", "fix the thing") };
  assert.equal(autostartPlan({ ...args, hasSession: false }).do, "terminal");
  assert.equal(autostartPlan({ ...args, hasSession: true }).do, "wait");
});

test("a chat that already has a session is still asked - its thread decides, not us", () => {
  const plan = autostartPlan({ autostart: { taskId: 7 }, selected: 7,
    detail: detailOf(7, "general", "Whats up"), hasSession: true });
  assert.equal(plan.do, "chat");
});

test("nothing happens without an autostart, or for a different task", () => {
  const detail = detailOf(7, "general", "Whats up");
  assert.equal(autostartPlan({ autostart: null, selected: 7, detail }).do, "wait");
  assert.equal(autostartPlan({ autostart: { taskId: 9 }, selected: 7, detail }).do, "wait");
  assert.equal(autostartPlan({ autostart: { taskId: 7 }, selected: 7, detail: null }).do, "wait");
});



test("every kind the assistant workspace handles is a chat", () => {
  for (const k of ["general", "Research", "marketing", "triage", "assistant", undefined])
    assert.equal(isGeneralKind(k), true, String(k));
  assert.equal(isGeneralKind("coding"), false);
  assert.equal(isGeneralKind("reply"), false);
});

test("Send to agent opens on the regular agent for the owner's task and a reply, the coding agent only for code (email walk 2026-10-29)", () => {
  for (const k of ["task", "reply", "general", "research", undefined]) assert.equal(opensOnRegular(k), true, String(k));
  assert.equal(opensOnRegular("coding"), false);
  // ...and a task or a reply is still not the assistant's conversation (general.handles): its view would refuse it
  assert.equal(isGeneralKind("task"), false);
});

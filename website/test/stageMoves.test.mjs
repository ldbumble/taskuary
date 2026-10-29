// THE STAGE MOVES RIDE ON THEIR PANE (the owner, 2026-10-29): where the task lays its panes the row keeps the task's own moves and hands
// Send to agent / Continue / Run another to Agent, Reply / Redraft / Hand it to a person to Close out, and Not a task / Remind me to Came
// from; a live agent's row is Stop and save alone.
import test from "node:test";
import assert from "node:assert/strict";
import { rowOf, splitRow, stageOf } from "../src/actionRow.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const ids = (r) => [...r.decide, ...r.agent, ...r.more].map((x) => x.id);
const task = [v("reply", "decide", { tone: "p", label: "Reply", spine: "Draft reply" }), v("send-general", "agent", { label: "Send to agent" }), v("done", "more"),
  v("hand", "more"), v("close-note", "more"), v("remind", "more"), v("nat", "more"), v("reshape", "more"), v("share", "more"), v("next", "next")];

test("each move's pane: the agent's, the reply's and the hand-off, where it came from - nothing of the task's own", () => {
  assert.deepEqual(task.map((x) => stageOf(x)), ["close", "agent", "", "close", "", "from", "from", "", "", ""]);
  assert.equal(stageOf(v("r12:redraft", "decide", { card: true })), "close", "a draft's own Redraft is Close out's");
  assert.equal(stageOf(v("save-end", "agent")), "", "Stop and save stays on the bar");
  assert.equal(stageOf(v("continue", "agent")), "agent");
  assert.equal(stageOf(v("run-another", "agent")), "agent");
});

test("with the panes laid the bar keeps the task's moves; the stage moves go to their pane, Draft reply its folded word", () => {
  const { row, by } = splitRow(rowOf({ ref: "TQ-1", list: task }), { live: false, open: "from" }, task);
  assert.deepEqual(ids(row).sort(), ["close-note", "done", "reshape", "share"].sort());
  assert.ok(row.next, "Next stays");
  assert.deepEqual(by.agent.map((x) => x.label), ["Send to agent"]);
  assert.deepEqual(by.close.map((x) => x.spine || x.label), ["Draft reply", "hand"]);
  assert.deepEqual(by.from.map((x) => x.id).sort(), ["nat", "remind"]);
});

test("a draft's Redraft stands for it on the spine, lit when it is the pick; Reply, which only opens the draft, steps aside", () => {
  const list = [...task, v("r12:redraft", "decide", { card: true, label: "Redraft" })];
  const { by } = splitRow(rowOf({ ref: "TQ-1", list }, { id: "r12:redraft" }), { live: false, open: "agent" }, list);
  assert.deepEqual(by.close.map((x) => [x.label, x.tone]), [["Redraft", "p"], ["hand", "s"]]);
});

test("a live agent's bar is Stop and save alone, Back and Next beside it", () => {
  const list = [v("save-end", "agent", { label: "Stop and save" }), v("diff", "agent"), v("run-another", "agent"), v("done", "more", { beside: true }), v("next", "next")];
  const { row, by } = splitRow(rowOf({ ref: "TQ-1", list }), { live: true, open: "agent" }, list);
  assert.deepEqual(ids(row), ["save-end"]);
  assert.ok(row.next);
  assert.deepEqual(by, {});
});

test("where no panes are laid (a phone, the Tasks tab) the row is as it was", () => {
  const r = rowOf({ ref: "TQ-1", list: task });
  assert.equal(splitRow(r, null, task).row, r);
});

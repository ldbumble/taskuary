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

test("with the panes laid the bar is Back and Next alone: the task's moves go to its title bar, the stage moves to their pane", () => {
  const { row, by } = splitRow(rowOf({ ref: "TQ-1", list: task }), { live: false, open: "from" }, task);
  assert.deepEqual(ids(row), [], "nothing but Back and Next on the bar");
  assert.ok(row.next, "Next stays");
  assert.deepEqual(by.head.map((x) => x.id), ["done", "close-note"], "Mark done first on the title bar");
  assert.deepEqual(by.change.map((x) => x.id), ["reshape"]);
  assert.deepEqual(by.share.map((x) => x.id), ["share"]);
  assert.deepEqual(by.agent.map((x) => x.label), ["Send to agent"]);
  assert.deepEqual(by.close.map((x) => x.spine || x.label), ["Draft reply", "hand"]);
  assert.deepEqual(by.from.map((x) => x.id).sort(), ["nat", "remind"]);
});

test("a draft's Redraft stands for it on the spine, lit when it is the pick; Reply, which only opens the draft, steps aside", () => {
  const list = [...task, v("r12:redraft", "decide", { card: true, label: "Redraft" })];
  const { by } = splitRow(rowOf({ ref: "TQ-1", list }, { id: "r12:redraft" }), { live: false, open: "agent" }, list);
  assert.deepEqual(by.close.map((x) => [x.label, x.tone]), [["Redraft", "p"], ["hand", "s"]]);
});

test("a live agent's bar is Back and Next; its Stop and save is on its pane's strip, and Mark done stays on Close out", () => {
  const list = [v("save-end", "agent", { label: "Stop and save" }), v("diff", "agent"), v("run-another", "agent"), v("done", "more", { beside: true }), v("next", "next")];
  const { row, by } = splitRow(rowOf({ ref: "TQ-1", list }), { live: true, open: "agent" }, list);
  assert.deepEqual(ids(row), []);
  assert.ok(row.next);
  assert.deepEqual(Object.keys(by).sort(), ["head", "live"]);
  assert.deepEqual(by.live.map((x) => x.id), ["save-end"]);
  // MARK DONE ALWAYS SHOWS ON CLOSE OUT (the owner, 2026-11-02): a parked or working agent's task offered only Stop and save
  assert.deepEqual(by.head.map((x) => x.id), ["done"], "Mark done, and only Mark done, of the task's own moves");
});

test("where no panes are laid (a phone, the Tasks tab) the row is as it was", () => {
  const r = rowOf({ ref: "TQ-1", list: task });
  assert.equal(splitRow(r, null, task).row, r);
});

test("a lit move on the title bar comes right after Mark done, so the bar's fold from its end never takes it", () => {
  const list = [...task, v("repo", "decide", { tone: "p", label: "Choose where the code is" })];
  const { by } = splitRow(rowOf({ ref: "TQ-1", list }), { live: false, open: "agent" }, list);
  const all = [...by.head, ...by.change].map((x) => x.id);
  assert.ok(all.includes("repo"), JSON.stringify(by));
  if (by.head.some((x) => x.id === "repo")) assert.deepEqual(by.head.slice(0, 2).map((x) => x.id), ["done", "repo"]);
});

// A REPORT LAYS EVERY MOVE ON ITS OWN PANE (the owner, 2026-10-31: "report should be white with buttons on it"): in its three sections on a
// desk the bar is Back and Next, and the report's pane carries its moves in the bar's order, the Change pill's and Share quiet after them
test("an item that lays all its moves on one pane leaves the bar Back and Next, its moves in the bar's order on that pane", () => {
  const all = { all: "report" };
  const list = [v("w:mine", "decide", { label: "Put it on my list", laid: all }), v("w:regular_agent", "decide", { label: "Send to agent", laid: all }),
    v("w:report_off", "more", { label: "Pause this report", laid: all }), v("share", "more", { label: "Share" }), v("next", "next", { laid: all })];
  const { row, by } = splitRow(rowOf({ ref: "", list }), all, list);
  assert.deepEqual(ids(row), [], "nothing but Back and Next on the bar");
  assert.ok(row.next, "Next stays");
  assert.deepEqual(Object.keys(by), ["report"]);
  assert.deepEqual(by.report.map((x) => [x.label, !!x.quiet]), [["Put it on my list", false], ["Send to agent", false], ["Pause this report", true], ["Share", true]]);
});

// ...SAVE A STAGE MOVE, ON THE SPINE OF ITS OWN SECTION (the owner, 2026-10-31: "why is there no buttons on the agent like send to agent?"):
// an FYI's Send to agent stands on its Agent; Should be a task and Not ours stay on Came from; a report, with no Agent section, keeps all
test("an item with an Agent section puts Send to agent on it; the rest stay on the pane it is about", () => {
  const all = { all: "from", keys: ["from", "agent", "close"] };
  const list = [v("w:mine", "decide", { label: "Should be a task", stage: "from", laid: all }), v("w:regular_agent", "decide", { label: "Send to agent", laid: all }),
    v("w:not_ours", "more", { label: "Not ours", laid: all }), v("next", "next", { laid: all })];
  const { row, by } = splitRow(rowOf({ ref: "", list }), all, list);
  assert.deepEqual(ids(row), []);
  assert.deepEqual(by.agent.map((x) => x.label), ["Send to agent"]);
  assert.deepEqual(by.from.map((x) => x.label), ["Should be a task", "Not ours"]);
  const rep = { all: "report", keys: ["from", "report", "close"] }, mine = [v("w:mine", "decide", { label: "Put it on my list" }), v("w:regular_agent", "decide", { label: "Send to agent" })];
  assert.deepEqual(Object.keys(splitRow(rowOf({ ref: "", list: mine }), rep, mine).by), ["report"], "a report has no Agent: all stay on it");
});

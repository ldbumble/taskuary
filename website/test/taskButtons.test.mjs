// ONE ROW OF TASK BUTTONS (the owner, 2026-11-06: "same place but can be on spine or on top if the agent spine is open but it should be one code
// easy to change"): one fixed order whatever the state, a move that does not apply absent, the rest keeping their places.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { taskButtons } from "../src/actionRow.js";

const v = (id, extra = {}) => ({ id, label: id, ...extra });
const ids = (list) => list.map((x) => (x.change ? "change" : x.v.id));

test("Mark done, Hand it to a person, Remind me, Not for me, Change - then the rest, gathered off every pane", () => {
  const by = { head: [v("close-note"), v("done")], from: [v("nat"), v("remind"), v("watch")], close: [v("hand"), v("reply", { tone: "p" })],
    share: [v("share")], change: [v("kind")] };
  assert.deepEqual(ids(taskButtons(by)), ["done", "hand", "remind", "nat", "change", "close-note", "watch", "reply", "share"]);
  // ...and by state: no Hand it to a person, a closed task's Reopen - the others keep their order
  assert.deepEqual(ids(taskButtons({ ...by, close: [v("reply")] })), ["done", "remind", "nat", "change", "close-note", "watch", "reply", "share"]);
  assert.deepEqual(ids(taskButtons({ head: [v("reopen")] })), ["reopen"]);
  assert.deepEqual(ids(taskButtons(by, (x) => x.id === "nat")), ["done", "hand", "remind", "change", "close-note", "watch", "reply", "share"]);
  assert.deepEqual(ids(taskButtons({ head: [v("done")], agent: [v("done")] })), ["done"], "drawn once");
});

test("the row is drawn once, where BUTTONS_AT says, and the spines carry none of a task's moves", () => {
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /export const BUTTONS_AT = "strip";/);
  assert.match(page, /const buttonsHere = \(k\) => BUTTONS_AT === "strip" && k === \(isOpen\("agent"\) \? "agent"/);
  assert.match(page, /\{!task \? <SpineMoves sec=\{sec\.key\} name=\{sec\.name\} home=\{home\} \/> : BUTTONS_AT === "spine" && sec\.key === "from" \? <TaskButtons spine \/> : null\}/);
});

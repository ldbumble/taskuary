import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { TASK_GROUPS, foldRow, groupOf, sectionsOf, taskButtons } from "../src/actionRow.js";

const v = (id, extra = {}) => ({ id, label: id, ...extra });
const ids = (list) => list.map((x) => (x.change ? "change" : x.v.id));
const grps = (list) => sectionsOf(list).map((s) => s.grp);

test("the grouping table: Finish, Pass on, Agent, More - every verb in one group, the listed ones where the owner put them", () => {
  assert.deepEqual(TASK_GROUPS.map(([g]) => g), ["finish", "later", "agent", "more"]);
  const all = TASK_GROUPS.flatMap(([, , ks]) => ks);
  assert.equal(new Set(all).size, all.length, "a verb is in one group only");
  for (const [k, g] of [["done", "finish"], ["reopen", "finish"], ["close-note", "finish"], ["hand", "later"], ["remind", "later"], ["nat", "later"],
    ["watch", "later"], ["run-another", "agent"], ["send-general", "agent"], ["diff", "agent"], ["attach", "agent"], ["share", "more"]]) assert.equal(groupOf(v(k)), g, k);
  assert.equal(groupOf("change"), "more");
  // ...a verb not listed goes by its kind, else More; a draft's own verbs (`<rid>:approve`) by their last part
  assert.equal(groupOf(v("coding_agent")), "agent");
  assert.equal(groupOf(v("r12:approve")), "finish");
  assert.equal(groupOf(v("kind")), "more");
  assert.equal(groupOf(v("something-new")), "more");
});

test("the order: by section, then the table's order, gathered off every pane", () => {
  const by = { head: [v("close-note"), v("done")], from: [v("nat"), v("remind"), v("watch")], agent: [v("hand"), v("reply", { tone: "p" }), v("run-another")],
    share: [v("share")], change: [v("kind")] };
  assert.deepEqual(ids(taskButtons(by)), ["done", "close-note", "hand", "remind", "nat", "watch", "run-another", "reply", "share", "change"]);
  assert.deepEqual(grps(taskButtons(by)), ["finish", "later", "agent", "more"]);
  // ...by state: no Hand it to a person, a closed task's Reopen in Mark done's place - the others keep their order
  assert.deepEqual(ids(taskButtons({ ...by, agent: [v("reply")] })), ["done", "close-note", "remind", "nat", "watch", "reply", "share", "change"]);
  assert.deepEqual(ids(taskButtons({ head: [v("close-note"), v("reopen")] })), ["reopen", "close-note"]);
  assert.deepEqual(ids(taskButtons(by, (x) => x.id === "nat")), ["done", "close-note", "hand", "remind", "watch", "run-another", "reply", "share", "change"]);
  assert.deepEqual(ids(taskButtons({ head: [v("done")], agent: [v("done")] })), ["done"], "drawn once");
  assert.deepEqual(ids(taskButtons({ head: [v("x2"), v("x1")] })), ["x2", "x1"], "unlisted ones as they came");
});

test("a hairline only between sections that have something in them", () => {
  assert.deepEqual(grps(taskButtons({ head: [v("done")], share: [v("share")] })), ["finish", "more"], "no Pass on, no Agent: one divider");
  assert.deepEqual(grps(taskButtons({ agent: [v("run-another")] })), ["agent"], "one section: no divider");
  assert.deepEqual(grps([]), []);
  const secs = sectionsOf(taskButtons({ head: [v("done"), v("close-note")], from: [v("remind")] }));
  assert.deepEqual(secs.map((s) => s.items.length), [2, 1]);
});

test("the fold goes from the right - More, then Agent, then Pass on - and never takes Mark done or the lit move", () => {
  const by = { head: [v("done"), v("close-note")], from: [v("remind"), v("nat")], agent: [v("run-another", { tone: "p" }), v("attach")], share: [v("share")], change: [v("kind")] };
  const row = taskButtons(by), fold = (n) => foldRow(row, n);
  assert.deepEqual(ids(fold(0).shown), ids(row));
  assert.deepEqual(ids(fold(2).out), ["share", "change"], "More first");
  assert.deepEqual(ids(fold(3).out), ["attach", "share", "change"], "then Agent - its lit move stays");
  assert.deepEqual(ids(fold(5).out), ["remind", "nat", "attach", "share", "change"], "then Pass on");
  assert.equal(fold(0).loose, 6);
  assert.deepEqual(ids(fold(99).shown), ["done", "run-another"], "Mark done and the lit move never fold");
  assert.deepEqual(ids(foldRow(taskButtons({ head: [v("reopen")], share: [v("share")] }), 9).shown), ["reopen"], "nor Reopen in Mark done's place");
});

test("one look: every task-row button is the same class, the lit one alone adds the fill, and the row is drawn once where BUTTONS_AT says", () => {
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /className=\{`tq-ab row\$\{v\.tone === "p" \? " p" : ""\}`\}/);
  assert.match(page, /<MovesLine items=\{items\} tucked=\{tucked\} sec="task" name="Task" even \/>/);
  assert.match(page, /import \{ ROW_LOOK \} from "\.\/ButtonBar\.jsx";/);
  assert.match(page, /const EVEN_ROW = \{ \.\.\.ROW_LOOK,/);
  assert.match(page, /export const BUTTONS_AT = "strip";/);
  assert.match(page, /const buttonsHere = \(k\) => BUTTONS_AT === "strip" && k === \(isOpen\("agent"\) \? "agent"/);
  assert.match(page, /\{!task \? <SpineMoves sec=\{sec\.key\} name=\{sec\.name\} \/> : BUTTONS_AT === "spine" && sec\.key === "from" \? <TaskButtons spine \/> : null\}/);
});

// the owner, 2026-11-06, of the New dialog's footer: "this is too thick. it should just be button wide and button should be on left ... Reusable
// code is always the best" - every dialog's actions are the task row's ButtonBar: no band, left, one button tall, the main move first
test("every dialog's actions are the one ButtonBar: one button size, left, no band", async () => {
  const { readdirSync } = await import("node:fs");
  const src = new URL("../src/", import.meta.url), files = readdirSync(src).filter((f) => f.endsWith(".jsx"));
  const read = (f) => readFileSync(new URL(f, src), "utf8");
  assert.deepEqual(files.filter((f) => /<DialogActions/.test(read(f))), [], "no dialog draws its own action band");
  const bar = read("ButtonBar.jsx");
  assert.match(bar, /export const ROW_BTN = \{ height: 28, minHeight: 28, minWidth: 0, px: 1\.5, py: 0, fontSize: 12,[^}]*borderRadius: 99/);
  assert.match(bar, /justifyContent: "flex-start"/);
  assert.doesNotMatch(bar, /borderTop|PANEL2/, "no band");
  for (const f of ["NewSheet.jsx", "HubView.jsx"]) {
    assert.match(read(f), /<ButtonBar>/, f);
    assert.doesNotMatch(read(f), /justifyContent: "flex-end", px: 3, py: 1\.75,\s*borderTop/, f);
  }
  // ...the main move first, Cancel after it
  assert.match(read("NewSheet.jsx"), /<ButtonBar>[\s\S]*?variant="contained"[\s\S]*?>Cancel<\/Button>\s*<\/ButtonBar>/);
});

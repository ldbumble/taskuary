// THE ACTION ROW (layout B): what it draws is decided by rowOf from the verbs the item on the table registered. These pin the
// promises the owner asked for (2026-09-30): one filled button at most, a greyed decision says why, Mark done is the decision only
// when nothing else is, a live session has no primary, and a press calls the card's LATEST handler.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { press, put, rowOf } from "../src/actionRow.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const filled = (r) => [...r.decide, ...r.agent, r.next].filter((x) => x && x.tone === "p").map((x) => x.id);

test("a decision waiting is the ONE filled button; Next is outlined beside it", () => {
  const r = rowOf({ ref: "TQ-1", list: [v("approve", "decide", { tone: "p", label: "Close out" }), v("alt", "decide"), v("done", "more"), v("next", "next")] });
  assert.deepEqual(filled(r), ["approve"]);
  assert.equal(r.next.tone, "s");
  assert.deepEqual(r.more.map((x) => x.id), ["done"], "Mark done steps back behind More when a decision is waiting");
});

test("nothing to decide: Mark done is the move, and Next stays outlined", () => {
  const r = rowOf({ ref: "", list: [v("done", "more"), v("nat", "more"), v("next", "next")] });
  assert.deepEqual(filled(r), ["done"]);
  assert.deepEqual(r.more.map((x) => x.id), ["nat"]);
});

test("the way back into an agent's session leads, and Mark done stands outlined beside it - not behind More", () => {
  const r = rowOf({ ref: "", list: [v("continue", "agent", { lead: true }), v("done", "more"), v("next", "next")] });
  assert.deepEqual(filled(r), ["continue"]);
  assert.deepEqual(r.agent.map((x) => [x.id, x.tone]), [["continue", "p"], ["done", "s"]]);
  assert.ok(!r.more.some((x) => x.id === "done"));
});

test("a live session has no primary: Mark done is not promoted, Next is the one filled button", () => {
  const r = rowOf({ ref: "", list: [v("save-end", "agent"), v("done", "more", { promote: false }), v("next", "next")] });
  assert.deepEqual(filled(r), ["next"]);
  assert.ok(r.more.some((x) => x.id === "done"));
});

test("a greyed decision says WHY, in the row, and Next is not a second filled button", () => {
  const r = rowOf({ ref: "TQ-1", list: [v("approve", "decide", { tone: "p", label: "Close out", disabled: true, why: "write the reply first" }), v("next", "next")] });
  assert.equal(r.why, "Close out is off - write the reply first");
  assert.deepEqual(filled(r), ["approve"]);
  assert.equal(rowOf({ ref: "", list: [v("approve", "decide", { tone: "p", label: "Close out" }), v("next", "next")] }).why, "");
});

test("a press calls the card's LATEST handler, not the one it registered first", () => {
  const calls = [];
  put("t", [{ ...v("x", "more"), run: () => calls.push("old") }]);
  put("t", [{ ...v("x", "more"), run: () => calls.push("new") }]);
  press("x");
  put("t", null);
  assert.deepEqual(calls, ["new"]);
  press("x");
  assert.deepEqual(calls, ["new"], "a verb whose card has gone does nothing");
});

test("the card's buttons leave the card on the canvas and come back on the Tasks tab", () => {
  const read = (n) => fs.readFileSync(path.join(process.cwd(), "src", n), "utf8");
  const task = read("TaskPage.jsx");
  assert.match(task, /const inRow = !!canvas/);
  assert.match(task, /useVerbs\("task"/);
  assert.match(read("ReviewDecision.jsx"), /\{!toRow && <>/, "the decision's own buttons are drawn only when it is not in the row");
  assert.doesNotMatch(read("CanvasItem.jsx"), /data-tq-next/, "Next is the row's now; the view carries none of its own");
  assert.match(read("ActionRow.jsx"), /data-tq-next/);
});

test("Decline says what goes out with it: the text in the box exactly as edited, or nothing when the box is empty", () => {
  const src = fs.readFileSync(path.join(process.cwd(), "src", "ReviewDecision.jsx"), "utf8");
  assert.match(src, /sends the text above exactly as you have it/);
  assert.match(src, /The box is empty, so nothing is sent/);
  assert.match(src, /`\$\{co\.alt\.label\} & send your text`/, "the label says it sends the owner's text only when there is text");
  assert.match(src, /reply_text: verb !== "reject" && sendable && value\.trim\(\) \? value : null/, "an empty box sends no reply - Decline only closes the pull request");
  assert.equal((src.match(/title=\{altTitle\}|title: altTitle/g) || []).length, 2, "the row's Decline and the card's carry the one sentence");
  assert.doesNotMatch(src, /disabled: busy \|\| \(sendable && !value\.trim\(\)\), run: \(\) => decideBoth\(co\.alt/, "Decline is not disabled by an empty box");
});

test("Next is the FIRST control of the row, and the ref label comes last", () => {
  const src = fs.readFileSync(path.join(process.cwd(), "src", "ActionRow.jsx"), "utf8");
  const at = (re) => src.search(re);
  assert.ok(at(/data-tq-next/) < at(/decide\.map\(btn\)/), "Next before the decision");
  assert.ok(at(/decide\.map\(btn\)/) < at(/data-tq-more/), "then the decision, then More");
  assert.ok(at(/data-tq-more/) < at(/data-tq-row-ref/), "the faint item label is last");
});

test("no rule above the chat line: the row and the composer float", () => {
  const css = fs.readFileSync(path.join(process.cwd(), "src", "assistantView.css"), "utf8");
  const rule = css.split("\n").find((l) => l.startsWith(".tq-compose {")) || "";
  assert.ok(rule && !/border-top/.test(rule), "the dock has no border-top");
});

test("a card's own <Button> is read into a row verb: its label, handler, disabled flag and ONE filled tone", async () => {
  const { default: React } = await import("react");
  const { movesOf } = await import("../src/actionRow.js");
  const calls = [];
  const h = React.createElement;
  const node = h(React.Fragment, null,
    h("div", { variant: "contained", onClick: () => calls.push("a"), title: "does a" }, "Open ", "Settings"),
    h("div", { variant: "contained", disabled: true, onClick: () => calls.push("b") }, "Second"),
    h("div", { variant: "outlined", href: "https://example.test/join" }, "Join"),
    h("div", { variant: "outlined" }, "No handler"));
  const v = movesOf(node);
  assert.deepEqual(v.map((x) => [x.label, x.tone, x.disabled]), [["Open Settings", "p", false], ["Second", "s", true], ["Join", "s", false]]);
  v[0].run({}); v[1].run({});
  assert.deepEqual(calls, ["a", "b"], "the card's own handler runs; nothing is re-implemented");
});

test("every card's move and foot ride in the row: YourMove and Foot register, the card draws none of them", () => {
  const src = fs.readFileSync(path.join(process.cwd(), "src", "assistantCards.jsx"), "utf8");
  assert.match(src, /useVerbs\("move", rowed \? movesOf\(go\) : null/);
  assert.match(src, /\.\.\.movesOf\(verb, "decide", "v"\)/);
  assert.match(src, /\{!rowed && \(verb \|\|/, "the foot's own move is not drawn twice");
  assert.match(src, /row: outer\.row/, "the walk's foot rides in the row as well");
  assert.match(fs.readFileSync(path.join(process.cwd(), "src", "ReplyFiles.jsx"), "utf8"), /toRow && mail/, "Attach a file is a More verb in the row");
  assert.match(fs.readFileSync(path.join(process.cwd(), "src", "TaskPage.jsx"), "utf8"), /id: "ask-sender", group: "more"/, "Ask sender is a More verb in the row");
});

test("Mark done and Remind me put the task down AT THE PRESS, as Next does, and a failure puts it back", () => {
  const read = (n) => fs.readFileSync(path.join(process.cwd(), "src", n), "utf8");
  const task = read("TaskPage.jsx"), remind = read("RemindMe.jsx"), view = read("AssistantView.jsx");
  const finish = task.slice(task.indexOf("const finish = async"), task.indexOf("const reminded ="));
  assert.ok(finish.indexOf("onLeave?.()") < finish.indexOf("runOperation"), "the close is asked for after the task is put down");
  assert.match(finish, /onStay\?\.\(msg\)/);
  assert.ok(remind.indexOf("onLeave?.()") < remind.indexOf("api.post"), "the reminder too");
  assert.match(remind, /if \(leaving\) onStay\?\.\(msg\)/);
  assert.match(view, /putDown: \(key\) => \{ setExpanded\(false\); setFoldedKey\(key\); setNextComing\(true\); \}/, "folded, and the … under it");
  assert.match(view, /onAfter=\{\(\) => actions\.advance\(null, true\)\}/, "the next one comes without the half-second of grace");
});

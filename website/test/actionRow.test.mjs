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
  // Mark done stays on the bar, outlined, beside the decision (the owner, 2026-10-06: "next to next on every single task")
  assert.deepEqual(r.agent.map((x) => [x.id, x.tone]), [["done", "s"]]); assert.deepEqual(r.more, []);
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
  assert.ok(r.agent.some((x) => x.id === "done" && x.tone === "s") && !r.more.some((x) => x.id === "done"));
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
  // ...but a decision's own buttons stay UNDER ITS DRAFT on every surface (the owner, 2026-10-06): none of them ride the row
  assert.doesNotMatch(read("ReviewDecision.jsx"), /\{!toRow && <>/);
  assert.match(read("ReviewDecision.jsx"), /\], false\);   \/\/ the draft's own buttons are drawn under it/);
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

test("a move on a PIECE stays on it; a move on the whole item rides the row (2026-10-06)", () => {
  const src = fs.readFileSync(path.join(process.cwd(), "src", "assistantCards.jsx"), "utf8");
  assert.match(src, /const rowed = false;/, "YourMove - a draft's send, an agent's answer - draws its button where it acts");
  assert.match(src, /\.\.\.movesOf\(verb, "decide", "v"\)/, "a Foot's move (All read, next on a batch) acts on the whole item: the row");
  assert.match(src, /\{!rowed && \(verb \|\|/, "...and is not drawn twice");
  assert.match(src, /i < 3 \|\| a\.verb === "close" \? "decide" : "more"/, "Mark done is never behind More");
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
  assert.match(view, /putDown: \(key, tid = null\) => \{ setExpanded\(false\); setFoldedKey\(key\); setNextComing\(true\); setLeavingTid\(tid\); \}/, "folded, and the … under it");
  // ...and off the RAIL at the press as well, a live session's Mark done included: it waited on an 18-second write-up
  // first, sitting under For later the whole time (the owner, 2026-10-01: "it first went to Later ... did not disappear")
  const stop = task.slice(task.indexOf("const stopAndFinish = async"), task.indexOf("const markDoneHint"));
  assert.ok(stop.indexOf("onLeave?.()") > -1 && stop.indexOf("onLeave?.()") < stop.indexOf("/wrap"), "put down before the write-up");
  assert.match(view, /onLeave=\{\(\) => canvas\.putDown\(c\.key, c\.tid\)\}/);
  assert.match(view, /items: asPressed\(pile\.items, \{ leaving: leavingTid/, "the rail drops it (funnelPile.asPressed)");
  assert.match(view, /!pile\.items\.some\(\(i\) => i\.tid === leavingTid\)\) setLeavingTid\(null\)/, "until the server's pile has let it go - a reopened task is never hidden");
  assert.match(view, /pickUp: \(key, why\) => \{[^\n]*setLeavingTid\(null\)/, "a failed close puts it back on the rail too");
  assert.match(view, /onAfter=\{\(\) => actions\.advance\(null, true\)\}/, "the next one comes without the half-second of grace");
});

test("a row, a task or an fyi puts the open browse view down AT THE CLICK, as one sidebar area replaces another (2026-10-01)", () => {
  const view = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
  assert.match(view, /if \(shown\[i\]\.role === "browse"\) return shown\[i\]\.down \? null : shown\[i\]\.id;/, "a put-down view is no longer the live one");
  assert.match(view, /const openTaskCard = \(req\) => \{\n\s+setRailOpen\(false\);[^\n]*browseDown\(\);/);
  assert.match(view, /setStageMode\("chat"\); browseDown\(\); surface\(key, asUser \|\| null\);/, "pull");
  assert.match(view, /const pullOrOpen = \(key, asUser, openByMid, openByItem\) => \{\n\s+browseDown\(\);/);
  assert.match(view, /\{ \.\.\.x, state, down: false \}/, "opening the same area again picks it back up");
  const browse = fs.readFileSync(path.join(process.cwd(), "src", "CanvasBrowse.jsx"), "utf8");
  assert.match(browse, /onOpenCard\?\.\(detail \? openLabel : where\)/, "the page itself is the context when nothing is opened on it");
});

test("every connector card is the same size: a 1px border with the live weight drawn inside, two lines held, a pill when connected", () => {
  const src = fs.readFileSync(path.join(process.cwd(), "src", "ConnectorsView.jsx"), "utf8");
  const card = src.slice(src.indexOf("const ConnCard"), src.indexOf("const ConnCard") + 2600);
  assert.match(card, /border: `1px solid \$\{st\.border\}`/);
  assert.doesNotMatch(card, /\$\{CARD_STATE\[connState\(c\)\]\.width\}px solid/, "no border that grows with the state");
  assert.match(card, /inset 0 0 0 \$\{extra\}px/);
  assert.match(card, /minHeight: "3em"/);
  assert.match(card, /c\.channel === "cli" \? "Installed" : "Connected"/);
});

test("on the canvas the task view SHRINKS to its box - no percentage height, so it can never draw over the next line (2026-10-01)", () => {
  const task = fs.readFileSync(path.join(process.cwd(), "src", "TaskPage.jsx"), "utf8");
  assert.match(task, /height: canvas \? "auto" : "calc\(100vh - 118px\)"/, "no height: 100% against a box that only has a max-height");
  assert.match(task, /\.\.\.\(canvas \? \{ boxSizing: "border-box", flex: "1 1 auto", display: "flex", flexDirection: "column" \}/);
  assert.match(task, /\.\.\.\(canvas \? \{ boxSizing: "border-box", flex: "1 1 auto", minHeight: 0 \} : \{ height: "100%" \}\)/);
  const item = fs.readFileSync(path.join(process.cwd(), "src", "CanvasItem.jsx"), "utf8");
  assert.match(item, /<Box sx=\{\{ flex: "1 1 auto", minHeight: 0, display: "flex", flexDirection: "column" \}\}>/);
});

test("a typed question is about what is OPEN on the table, whatever put it there (2026-10-01)", () => {
  const view = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
  assert.match(view, /const table = msgs\[interactiveCardIndex\(msgs\)\]\?\.card;/);
  assert.match(view, /const subject = openCardRef\.current \? null : \(tableKey \|\| current\);/);
  assert.match(view, /turn\(\{ mode: "say", text: t, key: subject,/);
});

// TWO WAYS TO CLOSE, ONE PLACE (the owner, 2026-10-05: "why is close with note not inside the more.. menu but mark done is in the
// menu?"): Close with a note is Mark done with words, so it stands right after Mark done wherever Mark done stands.
test("close with a note stands beside Mark done on the bar when a decision is waiting", () => {
  const r = rowOf({ ref: "TQ-1", list: [v("reply", "decide", { tone: "p" }), v("done", "more"), v("close-note", "more"), v("nat", "more"), v("next", "next")] });
  assert.deepEqual(r.decide.map((x) => x.id), ["reply"]);
  assert.deepEqual(r.agent.map((x) => x.id), ["done", "close-note"]); assert.deepEqual(r.more.map((x) => x.id), ["nat"]);
});

test("...beside it as the move when nothing else waits, outlined", () => {
  const r = rowOf({ ref: "", list: [v("close-note", "more"), v("done", "more"), v("nat", "more"), v("next", "next")] });
  assert.deepEqual(r.decide.map((x) => [x.id, x.tone]), [["done", "p"], ["close-note", "s"]]);
  assert.deepEqual(r.more.map((x) => x.id), ["nat"]);
});

test("...and beside it next to the way back into a session", () => {
  const r = rowOf({ ref: "", list: [v("continue", "agent", { lead: true }), v("done", "more"), v("close-note", "more"), v("next", "next")] });
  assert.deepEqual(r.agent.map((x) => x.id), ["continue", "done", "close-note"]);
  assert.ok(!r.more.some((x) => x.id === "close-note"));
});

test("the task page registers Close with a note with Mark done, not as a decision of its own", () => {
  const page = fs.readFileSync(path.join(process.cwd(), "src", "TaskPage.jsx"), "utf8");
  assert.match(page, /id: "close-note", group: "more"/);
});

// THE ROW INVENTORY (the owner, 2026-10-05): every Mark done has Close with a note beside it, no word stands twice, and a live
// session's Mark done is on the bar when there is room.
test("close with a note follows a draft's own Mark done too", () => {
  const r = rowOf({ ref: "", list: [v("812:approve", "decide", { tone: "p", label: "Close out" }), v("812:redraft", "decide", { label: "Redraft" }),
    v("812:done", "decide", { label: "Mark done", closes: true }), v("done", "more", { label: "Mark done" }), v("close-note", "more", { label: "Close with a note" }),
    v("nat", "more"), v("next", "next")] });
  assert.deepEqual(r.decide.map((x) => x.id), ["812:approve", "812:redraft", "812:done", "close-note"]);
  assert.ok(!r.more.some((x) => x.id === "close-note"));
});

test("no word stands twice: a word on the bar is not repeated, nor behind More", () => {
  const r = rowOf({ ref: "", list: [v("812:approve", "decide", { tone: "p", label: "Close out" }), v("812:remind", "decide", { label: "Remind me" }),
    v("m:Mark done", "decide", { label: "Mark done" }), v("w:close", "decide", { label: "Mark done" }),
    v("remind", "more", { label: "Remind me" }), v("nat", "more", { label: "Not a task" }), v("next", "next")] });
  const labels = [...r.decide, ...r.agent].map((x) => x.label);
  assert.equal(labels.filter((l) => l === "Mark done").length, 1);
  assert.ok(!r.more.some((x) => x.label === "Remind me"), "Remind me is on the bar already");
  assert.deepEqual(r.more.map((x) => x.label), ["Not a task"]);
});

test("a live session's Mark done stands on the bar, outlined, and Next stays the filled one - room or not", () => {
  const live = [v("diff", "agent", { label: "Review changes" }), v("save-end", "agent", { label: "Save and end session" }),
    v("run-another", "agent", { label: "Run another agent" }), v("done", "more", { label: "Mark done", promote: false, beside: true }), v("next", "next")];
  const r = rowOf({ ref: "", list: live });
  assert.deepEqual(r.agent.map((x) => x.id), ["diff", "save-end", "run-another", "done"]);
  assert.equal(r.agent.find((x) => x.id === "done").tone, "s");
  assert.equal(r.next.tone, "p");
  const full = rowOf({ ref: "", list: [v("a1", "agent"), v("a2", "agent"), v("a3", "agent"), v("a4", "agent"), ...live.slice(3)] });
  assert.ok(full.agent.some((x) => x.id === "done") && !full.more.some((x) => x.id === "done"), "never behind More (2026-10-06)");
});

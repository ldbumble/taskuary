// THE ACTION ROW (layout B): what it draws is decided by rowOf from the verbs the item on the table registered. These pin the
// promises the owner asked for (2026-09-30, 2026-10-17): one filled button at most and only the Advisor's pick, a greyed decision
// says why, Mark done leads when nothing else waits, and a press calls the card's LATEST handler.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { leaveRow, press, put, rowNow, rowOf, rowTable } from "../src/actionRow.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const filled = (r) => [...r.decide, ...r.agent, r.next].filter((x) => x && x.tone === "p").map((x) => x.id);

// NOTHING DARK UNTIL THE ADVISOR ANSWERS (the owner, 2026-10-17: "nothing dark until advisor ... keep it ai"): the row's own
// fallbacks - a card's filled tone, Mark done when nothing waits, the way back into a session, Next - are all outlined
test("no advice: a decision waiting is outlined, Next is outlined beside it - nothing on the row is dark", () => {
  const r = rowOf({ ref: "TQ-1", list: [v("approve", "decide", { tone: "p", label: "Close out" }), v("alt", "decide"), v("done", "more"), v("next", "next")] });
  assert.deepEqual(filled(r), []); assert.equal(r.primary, null);
  assert.equal(r.next.tone, "s");
  // Mark done stays on the bar, outlined, beside the decision (the owner, 2026-10-06: "next to next on every single task")
  assert.deepEqual(r.agent.map((x) => [x.id, x.tone]), [["done", "s"]]); assert.deepEqual(r.more, []);
  // ...and advised, the decision is the one dark button
  assert.deepEqual(filled(rowOf({ ref: "TQ-1", list: [v("approve", "decide", { tone: "p", label: "Send" }), v("done", "more"), v("next", "next")] },
    { verb: "approve", label: "Send" })), ["approve"]);
});

test("nothing to decide: Mark done leads the bar, outlined until the Advisor picks it", () => {
  const list = [v("done", "more"), v("nat", "more"), v("next", "next")];
  const r = rowOf({ ref: "", list });
  assert.deepEqual(filled(r), []);
  assert.deepEqual(r.decide.map((x) => x.id), ["done"]);
  assert.deepEqual(r.more.map((x) => x.id), ["nat"]);
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "close", label: "Mark done" })), ["done"]);
});

test("the way back into an agent's session leads, outlined, and Mark done stands outlined beside it - not behind More", () => {
  const r = rowOf({ ref: "", list: [v("continue", "agent", { lead: true }), v("done", "more"), v("next", "next")] });
  assert.deepEqual(filled(r), []);
  assert.deepEqual(r.agent.map((x) => [x.id, x.tone]), [["continue", "s"], ["done", "s"]]);
  assert.ok(!r.more.some((x) => x.id === "done"));
});

test("a live session: Mark done is not promoted, and Next is outlined too", () => {
  const r = rowOf({ ref: "", list: [v("save-end", "agent"), v("done", "more", { promote: false }), v("next", "next")] });
  assert.deepEqual(filled(r), []);
  assert.ok(r.agent.some((x) => x.id === "done" && x.tone === "s") && !r.more.some((x) => x.id === "done"));
});

test("a greyed decision says WHY, in the row, and nothing fills in its place", () => {
  const r = rowOf({ ref: "TQ-1", list: [v("approve", "decide", { tone: "p", label: "Close out", disabled: true, why: "write the reply first" }), v("next", "next")] });
  assert.equal(r.why, "Close out is off - write the reply first");
  assert.deepEqual(filled(r), []);
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

// ONE AT A TIME (the overnight walk, 2026-10-27): a double-click on Accept drafted the calendar's answer twice
test("a verb still answering is not run again for the same card, and runs again once it has answered", async () => {
  let n = 0, done;
  put("cal", [{ ...v("accept_invite", "decide"), run: () => { n++; return new Promise((r) => { done = r; }); } }]);
  press("accept_invite"); press("accept_invite");
  assert.equal(n, 1, "the second click of a double-click ran it again");
  done(); await new Promise((r) => setTimeout(r, 0));
  press("accept_invite");
  assert.equal(n, 2, "answered: the next press is a press");
  // ...a verb that answers at once (it opens a menu, a note) is never held
  let m = 0;
  put("cal", [{ ...v("close_note", "decide"), run: () => { m++; } }]);
  press("close_note"); press("close_note");
  assert.equal(m, 2);
  // ...and Next keeps the walk's own rules
  let x = 0;
  put("cal", [{ ...v("next", "next"), run: () => { x++; return new Promise(() => {}); } }]);
  press("next"); press("next");
  assert.equal(x, 2);
  put("cal", null);
});

test("the card's buttons leave the card on the canvas and come back on the Tasks tab", () => {
  const read = (n) => fs.readFileSync(path.join(process.cwd(), "src", n), "utf8");
  const task = read("TaskPage.jsx");
  assert.match(task, /const inRow = !!canvas/);
  assert.match(task, /useVerbs\("task"/);
  // ...but a decision's own buttons stay UNDER ITS DRAFT on every surface (the owner, 2026-10-06): none of them ride the row
  assert.doesNotMatch(read("ReviewDecision.jsx"), /\{!toRow && <>/);
  // ...registered as `card` verbs, so the row knows the card holds the move and never draws them (B4, 2026-10-17)
  assert.match(read("ReviewDecision.jsx"), /\.map\(\(v\) => \(\{ \.\.\.v, card: true \}\)\), toRow\);/);
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

test("Next is the FIRST control of the row, then the types; no task number or waiting words on it (2026-10-13)", () => {
  const src = fs.readFileSync(path.join(process.cwd(), "src", "ActionRow.jsx"), "utf8");
  const row = src.slice(src.indexOf("export default function ActionRow"));
  assert.ok(row.search(/data-tq-next/) < row.search(/fit\.groups\.map/), "Next before the types");
  assert.doesNotMatch(row, /data-tq-row-ref|waited/);
});

test("the row by type: two buttons each, the rest behind that type's own arrow, the filled one always in view", async () => {
  const { clustersOf, typeOf } = await import("../src/actionRow.js");
  const row = rowOf({ ref: "", list: [v("reply", "decide", { tone: "p", label: "Write reply" }), v("email", "agent", { label: "Send out results" }),
    v("hand", "more", { label: "Hand it to a person" }), v("continue", "agent", { label: "Continue" }), v("run-another", "agent"),
    v("save-end", "more"), v("done", "more"), v("close-note", "more"), v("remind", "more"), v("nat", "more"), v("next", "next")] });
  const g = Object.fromEntries(clustersOf(row).map((c) => [c.type, c]));
  assert.deepEqual(clustersOf(row).map((c) => c.type), ["reply", "agent", "close", "task"]);
  assert.deepEqual(g.reply.shown.map((x) => x.id), ["reply", "email"]); assert.deepEqual(g.reply.rest.map((x) => x.id), ["hand"]);
  assert.deepEqual(g.close.shown.map((x) => x.id), ["done", "close-note"]);
  assert.deepEqual([...g.task.shown, ...g.task.rest].map((x) => x.id).sort(), ["nat", "remind"]);
  // the Advisor's pick behind the arrow comes into view, filled
  const picked = clustersOf(rowOf({ ref: "", list: [v("continue", "agent", { label: "Continue" }), v("run-another", "agent"), v("save-end", "more", { label: "Stop and save" })] },
    { verb: "stop_agent", label: "Stop and save" }));
  assert.equal(typeOf({ id: "save-end" }), "agent");
  assert.ok(picked[0].shown.some((x) => x.id === "save-end" && x.tone === "p"));
  assert.equal(typeOf({ id: "123:approve" }), "reply");                 // a draft's own verbs, by the act
  assert.equal(typeOf({ id: "w:Make a task" }), "act");                  // a card's own words lead, unlabelled
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
  assert.match(src, /\.\.\.movesOf\(verb, moves \? "next" : "decide", "v"\)/, "a Foot's move acts on the whole item: the row - a batch's All read, next IS its Next");
  assert.match(src, /<Foot moves verb=\{<Button[\s\S]{0,200}onDone\?\.\(btn\("next", "batch"\)\)/, "the batch's verb is in the Next group (the design, phase A)");
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
  assert.ok(finish.indexOf("onLeave?.()") < finish.indexOf("completeTask("), "the close is asked for after the task is put down");
  assert.match(finish, /onStay\?\.\(msg\)/);
  assert.ok(remind.indexOf("onLeave?.()") < remind.indexOf("api.post"), "the reminder too");
  assert.match(remind, /if \(leaving\) onStay\?\.\(msg\)/);
  assert.match(view, /putDown: \(key, tid = null\) => \{ leave\(\{ key, tid \}\); leavingRef\.current = \{ key, tid \}; setExpanded\(false\); setFoldedKey\(key\); setNextComing\(true\); setLeavingTid\(tid\); drawNextEarlyRef\.current\?\.\(key\); \}/, "folded, and the next drawn under it");
  // ...and off the RAIL at the press as well, a live session's Mark done included: it waited on an 18-second write-up
  // first, sitting under For later the whole time (the owner, 2026-10-01: "it first went to Later ... did not disappear")
  const stop = task.slice(task.indexOf("const stopAndFinish = async"), task.indexOf("const markDoneHint"));
  assert.ok(stop.indexOf("onLeave?.()") > -1 && stop.indexOf("onLeave?.()") < stop.indexOf("writeUpThenClose("), "put down before the write-up");
  assert.match(view, /onLeave=\{\(\) => canvas\.putDown\(c\.key, c\.tid\)\}/);
  assert.match(view, /items: asPressed\(pile\.items, \{ leaving: leavingTid/, "the rail drops it (funnelPile.asPressed)");
  assert.match(view, /putDownLanded\(pile\.items, leavingTid\)\) setLeavingTid\(null\)/, "until the server's pile has let it go - or put it For later - a reopened task is never hidden");
  assert.match(view, /pickUp: \(key, why\) => \{[^\n]*setLeavingTid\(null\)/, "a failed close puts it back on the rail too");
  assert.match(view, /onAfter=\{\(\) => actions\.advance\(null, true\)\}/, "the next one comes without the half-second of grace");
});

test("a row, a task or an fyi puts the open browse view down AT THE CLICK, as one sidebar area replaces another (2026-10-01)", () => {
  const view = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
  assert.match(view, /if \(shown\[i\]\.role === "browse"\) return shown\[i\]\.down \? null : shown\[i\]\.id;/, "a put-down view is no longer the live one");
  // a task opened by name goes the rail's road (pull, below) - a busy walk waits for it; a walk on the phone no longer lands a bare card (2026-10-23)
  assert.match(view, /const openTaskCard = \(req\) => \{[\s\S]{0,400}?pull\(`task:\$\{req\.tid\}`\); return;\n\s+\}\n\s+openLater\.current = req;\n\s+\};/);
  // ...and a task asked for while a turn is in flight (the Assistant's own link to it, a Board press during Next) waits for that turn and
  // then goes the same road - the bare card it landed as rang no rail row (the dead-end walk's RING, 2026-10-20)
  assert.match(view, /if \(busy \|\| resetting \|\| !openLater\.current\) return;\n\s+const req = openLater\.current; openLater\.current = null;\n\s+if \(req\.kind === "msg"\) openMsgRef\.current\?\.\(req\.mid\); else if \(req\.kind === "pull"\) pullRef\.current\?\.\(req\.key, req\.asUser\); else openTaskRef\.current\?\.\(req\);\n\s+\}, \[busy, resetting\]\);/);
  // ...and a rail row clicked mid-turn waits in the same one slot - the latest ask wins - where it was refused as busy and did nothing
  assert.match(view, /if \(!resetting && \(busy \|\| turnFlight\.current\)\) \{ openLater\.current = \{ kind: "pull", key, asUser \}; return; \}/);
  assert.match(view, /if \(old\) setOld\(null\); browseDown\(\); surface\(key, asUser \|\| null\);/, "pull");
  // ...and a message asked for by id (a card's link, #msg=) goes the same road, as its own card - waiting out a turn as a task does
  assert.match(view, /const openMsgCard = \(mid\) => \{\n\s+if \(!mid\) return;\n\s+if \(busy \|\| resetting \|\| turnFlight\.current\) \{ openLater\.current = \{ kind: "msg", mid \}; return; \}\n\s+pull\(`msg:\$\{mid\}`\);/);
  assert.doesNotMatch(view, /pullOrOpen|openByMid|openByItem/, "no road opens a row anywhere but on the canvas");
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
  assert.match(card, /data-tq-conn-pill[\s\S]{0,200}>Connected<\/Box>/);   // one word: the CLI card is on only when one is connected (cliCard.js)
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
  assert.match(view, /const table = msgs\[tableCardIndex\(msgs, current \|\| cardRef\.current\)\]\?\.card;/);   // the table's own card (tableCard.test)
  // ...a page open beside it included: it does not take the item off the table (verify, 2026-10-19)
  assert.match(view, /const subject = tableKey \|\| current \|\| cardRef\.current;/);
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
  assert.deepEqual(r.decide.map((x) => [x.id, x.tone]), [["done", "s"], ["close-note", "s"]]);
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

test("a live session's Mark done stands on the bar, outlined, and Next is outlined too - room or not", () => {
  const live = [v("diff", "agent", { label: "Review changes" }), v("save-end", "agent", { label: "Stop and save" }),
    v("run-another", "agent", { label: "Run another agent" }), v("done", "more", { label: "Mark done", promote: false, beside: true }), v("next", "next")];
  const r = rowOf({ ref: "", list: live });
  assert.deepEqual(r.agent.map((x) => x.id), ["diff", "save-end", "run-another", "done"]);
  assert.equal(r.agent.find((x) => x.id === "done").tone, "s");
  assert.equal(r.next.tone, "s");
  const full = rowOf({ ref: "", list: [v("a1", "agent"), v("a2", "agent"), v("a3", "agent"), v("a4", "agent"), ...live.slice(3)] });
  assert.ok(full.agent.some((x) => x.id === "done") && !full.more.some((x) => x.id === "done"), "never behind More (2026-10-06)");
});

test("a draft waiting under the card holds the move: the bar fills nothing - not Start an agent, not Next", () => {
  // the UX review, 2026-10-07: a drafted reply wore a filled Send on the card AND a filled Start an agent on the bar
  const r = rowOf({ ref: "TQ-3", list: [v("start-agent", "agent", { lead: true }), v("done", "more", { promote: false, onCard: true }), v("next", "next")] });
  assert.deepEqual(filled(r), []);
  assert.equal(r.next.tone, "s");
});

test("how long it has waited on you: owed lanes only, from an hour, in the rail's own bands", async () => {
  const { waitedText } = await import("../src/funnelPile.js");
  const now = Date.parse("2026-10-07T12:00:00"), at = (h) => new Date(now - h * 3600e3).toISOString();
  assert.equal(waitedText({ lane: "blocked", since: at(3) }, now), "waiting 3h");
  assert.equal(waitedText({ lane: "approve", when: at(50) }, now), "waiting 2d");
  assert.equal(waitedText({ lane: "approve", when: at(0.2) }, now), "");          // new is not "waiting"
  assert.equal(waitedText({ lane: "report", when: at(5) }, now), "");             // a report owes nobody
  assert.equal(waitedText({ lane: "theirs", when: at(5) }, now), "");             // waiting on THEM is not on you
});

test("one name per button: the bar says the label itself, no short bar word (buttons.json, 2026-10-17)", async () => {
  const mod = await import("../src/actionRow.js");
  assert.equal(mod.shortLabel, undefined, "no second, shorter name for the bar");
  const src = fs.readFileSync(path.join(process.cwd(), "src", "ActionRow.jsx"), "utf8");
  assert.match(src, />\{v\.label\}<\/button>/);
  assert.doesNotMatch(src, /\bSHORT\b|shortLabel/);
  const view = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
  assert.doesNotMatch(view, /tq-compose-hint|Enter sends · Shift\+Enter/);           // no hint under the box
});

test("one border around the three layers: the suggestion, the row and the box sit in one dock (2026-10-13)", () => {
  const view = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
  const dock = view.slice(view.indexOf('<div className="tq-dock">'), view.indexOf("<Popover open={!!emojiEl}"));
  for (const part of ["<AdvisorNext", "<ActionRow", 'className="tq-compose-box"']) assert.ok(dock.includes(part), part);
  const css = fs.readFileSync(path.join(process.cwd(), "src", "assistantView.css"), "utf8");
  assert.match(css, /\.tq-dock \{[^}]*border: 1px solid/);
  assert.match(css, /\.tq-dock \.tq-compose-box \{[^}]*border: 0;/);
});

// The draft's own Send lives UNDER THE DRAFT only (the owner, 2026-10-22, reversing the bar's copy of 2026-10-19), and the bar keeps no
// empty slot for it (2026-10-25: "we should not have empty space here"). Advised, it is lit on the card, the bar unchanged.
test("the draft's own Send is never on the bar and leaves no empty slot; advised it is lit on the card, the bar unchanged", async () => {
  const { advisedAny, advisedIn, clustersOf, holdsMove } = await import("../src/actionRow.js");
  const list = [v("12:approve", "decide", { tone: "p", label: "Send", card: true }), v("12:redraft", "decide", { label: "Redraft", card: true }),
    v("remind", "more", { label: "Remind me" }), v("done", "more", { promote: false, onCard: true, label: "Mark done" }), v("next", "next")];
  assert.ok(holdsMove(list));
  assert.equal(advisedAny(list, { verb: "approve", label: "Send" })?.id, "12:approve", "found, so no advice:approve is drawn");
  assert.equal(advisedIn(list, { verb: "approve", label: "Send" })?.id, "12:approve", "the Advisor's line finds the Send under the draft");
  const quiet = rowOf({ ref: "", list });
  assert.deepEqual([...quiet.decide, ...quiet.agent, ...quiet.more].filter((x) => x.card).map((x) => x.id), [], "no card verb on the bar - not Send, not Redraft");
  assert.ok(![...quiet.decide, ...quiet.agent, ...quiet.more].some((x) => x.slot || String(x.id).startsWith("slot:")), "no empty slot on the bar");
  // ...in the reply group, where the Send stood, and never behind ▾
  const reply = clustersOf(quiet).find((g) => g.type === "reply");
  assert.ok(!clustersOf(quiet).some((g) => [...g.shown, ...g.rest].some((x) => x.slot)), reply ? "the reply group holds only real buttons" : "");
  assert.deepEqual(filled(quiet), []);
  const sent = rowOf({ ref: "", list }, { verb: "approve", label: "Send" }), ids = (r) => [...r.decide, ...r.agent, ...r.more].map((x) => x.id);
  assert.deepEqual(filled(sent), []); assert.equal(sent.lit, "12:approve", "lit where it stands, under the draft"); assert.equal(sent.next.tone, "s");
  const row = fs.readFileSync(path.join(process.cwd(), "src", "ActionRow.jsx"), "utf8");
  assert.doesNotMatch(row, /data-tq-slot/, "no empty slot is drawn");
  assert.equal(rowOf({ ref: "", list }, { verb: "redraft", label: "Redraft" }).lit, "12:redraft", "a card verb with no slot is lit on the card");
  assert.deepEqual(ids(sent), ids(quiet), "the bar is the same with and without the advice");
  const later = rowOf({ ref: "", list }, { verb: "defer", label: "Remind me" });
  assert.deepEqual(later.more.filter((x) => x.tone === "p").map((x) => x.id), ["remind"], "an advised Remind me is filled where it stands");
  assert.deepEqual(ids(later), ids(quiet)); assert.equal(later.lit, "");
  // ...and the draft's own buttons under it are outlined while the row carries the item, but the one the Advisor lit
  assert.match(fs.readFileSync(path.join(process.cwd(), "src", "ReviewDecision.jsx"), "utf8"), /const solid = toRow && lit !== no\("approve"\) \? "outlined" : "contained";/);
});

test("the Advisor's own button for a move the row lacks is the dark one; a 409 says the suggestion changed", async () => {
  const strip = fs.readFileSync(path.join(process.cwd(), "src", "ActionRow.jsx"), "utf8");
  assert.match(strip, /group: "more", tone: "p", disabled: going,/);
  assert.match(strip, /status === 409 \? "This changed - here's the updated suggestion\."/);
  assert.doesNotMatch(strip, /note\.model/, "no model names in the Why? box");
  assert.doesNotMatch(strip, /e\.label \|\| e\.id/, "no evidence ids in the Why? box");
});

// issue 263 / the UI audit (2026-10-21): two mounted copies of one card registered under one name, cleared each other's verbs on
// every put, re-drew each other forever and React stopped the app (#185). Each copy is now its own owner, and the row shows one
// button per id however many copies carry it.
test("two copies of a card carrying the same verb show one button, and either going leaves the other's", () => {
  const v = (n) => ({ id: "t263:send", label: "Send", group: "decide", run: () => n });
  put("t263-card:r1:", [v(1)]); put("t263-card:r2:", [v(2)]);
  assert.equal(rowNow().list.filter((x) => x.id === "t263:send").length, 1);
  put("t263-card:r2:", null);
  assert.equal(rowNow().list.filter((x) => x.id === "t263:send").length, 1);
  put("t263-card:r1:", null);
  assert.equal(rowNow().list.filter((x) => x.id === "t263:send").length, 0);
});

test("every mounted card registers under its own key, never a name another copy shares", () => {
  const src = fs.readFileSync(path.join(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "../src/actionRow.js"), "utf8");
  const body = src.slice(src.indexOf("export function useVerbs"), src.indexOf("}", src.indexOf("export function useVerbs")) + 1);
  assert.match(body, /useId\(\)/);
  assert.doesNotMatch(body, /put\(owner,/);
});

// THE LIT BUTTON FOLLOWS THE LINE (the UI audit's C2, 2026-10-21): a running agent's Stop and save darkens itself only while the
// Advisor has said nothing at all. Once the strip says something - "An agent is working on this - it says when it needs you", or
// "Connect an AI" - the button lit is that line's move, and Stop and save stays outlined: it invited stopping an agent that needed nothing.
test("a working agent's Stop and save is dark only when the strip says nothing; a line lights its own move", () => {
  const list = [v("save-end", "agent", { fill: true }), v("done", "more", { promote: false }), v("next", "next")];
  assert.deepEqual(filled(rowOf({ ref: "", list })), ["save-end"], "nothing said: the row's own move");
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "next" })), ["next"], "'it says when it needs you': Next, and only Next");
  assert.deepEqual(filled(rowOf({ ref: "", list }, { verb: "ai" })), [], "'Connect an AI': its own chip is the move, nothing on the row");
});

// SWITCHING TASKS (the owner, 2026-10-26: "fix switching tasks thing of course"): the old task's Send stood on the row under the next task
// until its card's cleanup ran. The row draws a card's verbs only while the table is its item, and none of the item a press is leaving
test("the row draws only the table's own verbs: another item's go the moment the table moves, and a press that fails gives them back", () => {
  const ran = [];
  put("card:a", [{ id: "approve", group: "decide", label: "Send", run: () => ran.push("a") }], "TQ-0001", "task:1");
  put("next:x", [{ id: "next", group: "next", label: "Next", run: () => {} }]);
  const ids = () => rowNow().list.map((x) => x.id);
  rowTable("task:1");
  assert.deepEqual(ids(), ["approve", "next"]);
  assert.equal(rowNow().list[0].at, "task:1", "a button says which item it was drawn for");
  leaveRow("task:1");
  assert.deepEqual(ids(), ["next"], "a press moving on: Next alone, nothing of the item it leaves");
  leaveRow(null);
  assert.deepEqual(ids(), ["approve", "next"], "the press failed: its buttons are back");
  rowTable("task:2");
  assert.deepEqual(ids(), ["next"], "the table moved: the old card, still mounted, draws nothing");
  // ...and the new card's Send, registered before the old one let go of the same id, is the one drawn and the one a press runs
  put("card:b", [{ id: "approve", group: "decide", label: "Send", run: () => ran.push("b") }], "TQ-0002", "task:2");
  put("card:a", [{ id: "approve", group: "decide", label: "Send", run: () => ran.push("a") }], "TQ-0001", "task:1");
  const send = rowNow().list.find((x) => x.id === "approve");
  assert.equal(send.at, "task:2");
  assert.equal(rowNow().ref, "TQ-0002");
  press("approve", null, null, send.of);
  assert.deepEqual(ran, ["b"], "the press acts on the task on the table, never the one put down");
  for (const o of ["card:a", "card:b", "next:x"]) put(o, null);
  rowTable(null);
});

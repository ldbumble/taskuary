// THE BASIC FLOW ON THE PAGE (the owner, 2026-11-12: "have you ever seen a chat that you type something new and the past agent turn changes.
// of course not ... nothing ever goes backwards"): the server's list keeps it (conversation.flow_breaks, run over every list the python
// corpora build); the page must not undo it with its own caches or its own lines. Invented people only.
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { flowBreaks, newerList, waitingChips, withMine } from "../src/chatStream.js";

const mail = { id: "m:1", kind: "arrival", words: "Can you make Thursday?" };
const answer = { id: "t:m:1:0", kind: "turn", state: "done", text: "Drafted a yes.", steps: [], cards: [{ id: "r:1", review: 1, status: "pending" }] };

test("back on a task, the list asked last is drawn - never an older one over it", () => {
  const left = { items: [mail, answer], working: false, _at: 1000 };
  const ahead = { items: [mail, { ...answer, cards: [{ id: "r:1", review: 1, status: "passed" }] }, { id: "l-2", kind: "line", text: "try now" }], working: true, _at: 2000 };
  assert.equal(newerList(left, ahead), ahead);
  assert.equal(newerList(ahead, left), ahead);
  assert.equal(newerList(null, left), left);
  assert.deepEqual(flowBreaks(newerList(left, ahead), left), []);
});

test("his line sent at rest stands over the turn it began, even when the read already has that turn starting", () => {
  const read = { items: [mail, answer, { id: "t:0:1:1", kind: "turn", state: "starting", text: "", steps: [], cards: [] }], pending: [], working: true };
  const got = withMine(read, [{ id: "l-2", kind: "line", text: "try now", at: new Date(), rest: true }]);
  assert.deepEqual(got.items.map((x) => x.id), ["m:1", "t:m:1:0", "l-2", "t:0:1:1"]);
  assert.deepEqual(flowBreaks(got), []);
  // ...and the old merge, line under the dots, is what the rule names
  assert.match(flowBreaks({ items: [mail, answer, read.items[2], { id: "l-2", kind: "line", text: "try now" }] })[0], /^a: the turn at work/);
});

test("his line sent at rest has the turn it begins under it even in the beat the server says working and has no turn yet", () => {
  const got = withMine({ items: [mail, answer], pending: [], working: true }, [{ id: "l-2", kind: "line", text: "try now", at: new Date(), rest: true }]);
  assert.deepEqual(got.items.map((x) => [x.id, x.state || ""]), [["m:1", ""], ["t:m:1:0", "done"], ["l-2", ""], ["t:l-2:0", "starting"]]);
});

test("his line greys the reply card above it in the same frame, before the server's read is back", () => {
  const card = { id: "r:1", review: 1, what: "draft_reply", status: "pending", was: { text: "Hi Gail, yes." } };
  const read = { items: [mail, { ...answer, cards: [card] }], pending: [], working: false };
  const got = withMine(read, [{ id: "l-2", kind: "line", text: "try now", at: new Date(), rest: true }]);
  assert.deepEqual(got.items[1].cards.map((c) => c.status), ["passed"]);
  assert.deepEqual(withMine(read, []).items[1].cards.map((c) => c.status), ["pending"]);     // ...and only then
});

// ...THE SAME CARD, ITS BUTTONS GREYED, NO REASON (the owner, 2026-11-18: "don't need reason. just keep it with buttons but the buttons grayed
// out once you moved on"): greyed from the frame he presses Enter, and no sentence of why rides on it for the chat to draw
test("his line greys the card above it in the same frame, with no reason line", () => {
  const card = { id: "r:1", review: 1, what: "draft_reply", status: "pending", was: { text: "Hi Gail, yes." }, aside: 'Not sent - you wrote "{line}" after it' };
  const read = { items: [mail, { ...answer, cards: [card] }], pending: [], working: false };
  const got = withMine(read, [{ id: "l-2", kind: "line", text: "what is on my plate today", at: new Date(), rest: true }]);
  assert.deepEqual(got.items[1].cards[0], { ...card, status: "passed" });
});

// ...A CARD OF SEVERAL EMAILS TOO (the real-CLI card walk, 2026-11-18): it carries no draft words of its own, so the page left it lit under his
// new line for a read (~230 ms) - two Sends to press over the line that had just set them aside. The server's `aside` says it greys
test("his line greys a card of several emails above it from the same frame", () => {
  const card = { id: "r:2", review: 2, what: "batch", batch: "b1", n: 2, status: "pending", aside: 'Not sent - you wrote "{line}" after it' };
  const read = { items: [mail, { ...answer, cards: [card] }], pending: [], working: false };
  const got = withMine(read, [{ id: "l-2", kind: "line", text: "draft them again", at: new Date(), rest: true }]);
  assert.equal(got.items[1].cards[0].status, "passed"); assert.equal(got.items[1].cards[0].why, undefined);
});

test("a line whose send failed stays where it stands in his own words; the failure is one line under it with Try again", async () => {
  const read = { items: [mail, answer], pending: [], working: false };
  const got = withMine(read, [{ id: "l-2", kind: "line", text: "try now", at: new Date(), rest: true, err: "The agent did not start" }]);
  assert.deepEqual(got.items.map((x) => x.id), ["m:1", "t:m:1:0", "l-2"]);          // in place, no turn under it, never by the box
  assert.deepEqual(got.pending, []);
  const src = await readFile(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(src, /\$\{x\.text\} - \$\{x\.err\}/, "an error is never glued into his words");
  assert.match(src, /data-tq-line-failed="">\{x\.err\}\{retry && <> · <button type="button" className="tq-aui-arrived-more-btn"\n\s+data-tq-try-again=""/);
});

test("what came in waits as a count on its sender's chip, his outside replies as their own, each naming the items it stands for", () => {
  const p = [{ id: "m:5", kind: "arrival", who: "Cat Priem", channel: "email" }, { id: "m:6", kind: "arrival", who: "Cat Priem", channel: "email" },
    { id: "m:7", kind: "arrival", who: "Gail Moreno", channel: "email" }, { id: "m:8", kind: "arrival", own: true, who: "You", channel: "whatsapp" },
    { id: "l-9", kind: "line", text: "and the dates" }];
  assert.deepEqual(waitingChips(p, "From Cat Priem"), [
    { key: "From Cat Priem", came: true, ids: ["m:5", "m:6"], label: "From Cat Priem · 2 new" },
    { key: "From Gail Moreno", came: false, ids: ["m:7"], label: "From Gail Moreno · 1 new" },
    { key: "You on WhatsApp", came: false, ids: ["m:8"], label: "You on WhatsApp · 1" }]);
});


test("nothing drawn goes or moves, and nothing new is drawn above it", () => {
  const was = { items: [mail, answer] };
  assert.deepEqual(flowBreaks({ items: [mail, answer, { id: "l-2", kind: "line", text: "x" }] }, was), []);
  assert.match(flowBreaks({ items: [mail, { id: "p:9", kind: "press", text: "You sent it." }, answer] }, was)[0], /^f: p:9 is drawn above/);
  assert.match(flowBreaks({ items: [mail] }, was)[0], /^c: t:m:1:0 was on the canvas and is gone/);
});


test("a turn at work says what is happening, or what we wait for, beside its dots - one line, on every level", async () => {
  const { workingLine } = await import("../src/chatStream.js");
  const label = (s) => (s.status === "running" ? s.doing : s.summary);
  const parts = [{ type: "work", steps: [{ summary: "Read invoices.csv", status: "done" }] }, { type: "said", text: "x" },
    { type: "work", steps: [{ summary: "Ran a command", doing: "Running a command", status: "running" }] }];
  assert.equal(workingLine(parts, label), "Running a command");
  // ...and what we wait for, where no step runs: the model writing, a session opening, his press (waitingOn)
  assert.equal(workingLine([{ type: "work", steps: [{ summary: "Read a.csv", status: "done" }] }], label), "Thinking…");
  assert.equal(workingLine([], label, { starting: true }), "Waiting for the agent to start");
  // ...on the chat's first turn only: a later one starting again is the work going on - no words of the app's (the owner, 2026-11-16), and
  // never bare dots either (the walks, 2026-11-17): it reads as the turn it becomes, its agent at work - a later one OPENING is not `later` (ConvTurn)
  assert.equal(workingLine([], label, { starting: true, later: true }), "Thinking…");
  // ...and while it thinks, the thought's latest words (chatlog._now `thinking`) - never a bare "Thinking…" for minutes (the owner, 2026-11-16) -
  // the one place a thought reads: it is never a row (the owner, 2026-11-23)
  const thinking = "The owner wants two bakeries. Tatte opens at 7 on Sundays, so I should check Bakey next.";
  assert.equal(workingLine([{ type: "work", steps: [{ summary: "Read a.csv", status: "done" }] }], label, { thinking }), "Tatte opens at 7 on Sundays, so I should check Bakey next");
  assert.equal(workingLine([], label, { thinking }), "Tatte opens at 7 on Sundays, so I should check Bakey next");
  const { thinkingLine } = await import("../src/chatStream.js");
  assert.ok(thinkingLine("word ".repeat(80)).length <= 110);
  // ...and the answer it is writing is its own row, streamed into it (the owner, 2026-11-23) - never a second copy on this line
  assert.equal(workingLine([{ type: "said", text: "Option one is Salem. Option two is" }], label, { doing: "Option one is Salem. Option two is" }), "Thinking…");
  assert.equal(workingLine(parts, label, { ask: "Waiting for your Allow once" }), "Waiting for your Allow once");
  const { waitingOn } = await import("../src/chatStream.js");
  assert.equal(waitingOn({ permissions: [{}] }), "Waiting for your Allow once");
  assert.equal(waitingOn({ asking: { ask: "signin", site: "bank.example" } }), "Waiting for you to sign in");
  assert.equal(waitingOn({ asking: { request_id: "q1" } }), "", "a question asked before is no wait while it works");
  assert.equal(waitingOn({}), "");
});


// ...ONE TABLE WORDS A STEP AT WORK (rule 3): the edit row's running verbs were a pair of its own beside agentSteps' ING; it reads them from there
test("an edit's running verb is the one table's, never words of its own", async () => {
  const { editRow } = await import("../src/chatStream.js");
  assert.equal(editRow({ name: "Write", file: "notes.md", edit: "", running: true }).summary, "Writing notes.md");
  assert.equal(editRow({ name: "Edit", file: "a/budget.py", edit: "", running: true }).summary, "Editing budget.py");
  const src = await readFile(new URL("../src/chatStream.js", import.meta.url), "utf8");
  assert.doesNotMatch(src.slice(src.indexOf("export const editRow"), src.indexOf("// THE PLAN IS A CHECKLIST")), /"Writing"|"Editing"/);
});

test("an edit still being made is \"Editing x\" in its row and on the working line - never \"Edited x (+1 -1)\" over \"Thinking...\"", async () => {
  const { eventsOf, turnParts, workingLine } = await import("../src/chatStream.js");
  const label = (s) => (s.status === "running" ? s.doing : s.summary);
  const steps = [{ k: "tool", name: "Read", args: { file_path: "a.py" }, status: "completed" },
    { k: "tool", name: "Edit", args: { file_path: "budget.py", old_string: "a", new_string: "b" }, status: "in_progress" }];
  const live = turnParts(eventsOf(steps, true), { live: true });
  assert.equal(live.at(-1).summary, "Editing budget.py");
  assert.equal(workingLine(live, label), "Editing budget.py");
  // ...made once its call returned, or once the turn is over
  const made = turnParts(eventsOf([steps[0], { ...steps[1], status: "completed" }], true), { live: true });
  assert.equal(made.at(-1).summary, "Edited budget.py (+1 −1)");
  assert.equal(workingLine(made, label), "Thinking…");
  assert.ok(!turnParts(eventsOf(steps, false)).some((p) => p.type === "edit"), "one that never returned is no edit made once the turn is over");
});

test("the working line names what no row in sight says - at every beat of a turn, its fold shut or opened, on the chat and the dock", async () => {
  // The status walk, 2026-11-18: a thought stood as its row and again on the line under it; a thought then a finished edit read the old
  // thought's words, the edit newer than it; and with the fold opened, "Reading budget.md" / "Editing budget.py" stood as a row and on the line
  const { workingLine, editRow } = await import("../src/chatStream.js");
  const { stepLabel } = await import("../src/agentSteps.js");
  const read = (status) => ({ kind: "read", status, summary: "Read budget.md" });
  const edit = (running) => editRow({ name: "Edit", file: "budget.py", edit: { old_string: "a = 1", new_string: "a = 2" }, running });
  const beat = (parts, open = false) => workingLine(parts, stepLabel, { open });
  // a step at work: shut in its fold, the line names it; the fold opened, its row says it with its spinner
  assert.equal(beat([{ type: "work", steps: [read("done"), read("running")] }]), "Reading budget.md");
  assert.equal(beat([{ type: "work", steps: [read("done"), read("running")] }], true), "Working…");
  // an edit being made: the same (4bce367's "Editing budget.py" under the shut fold)
  assert.equal(beat([{ type: "work", steps: [read("done")] }, edit(true)]), "Editing budget.py");
  assert.equal(beat([{ type: "work", steps: [read("done")] }, edit(true)], true), "Working…");
  // an edit that has been made, nothing newer: the model is at it again
  assert.equal(beat([{ type: "work", steps: [read("done")] }, edit(false)]), "Thinking…");
  // ConvTurn reads the open state of the fold the newest work is in (its first part's key, chatStream.runsOf), and the dock's trail as always open
  const src = await readFile(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /const folded = useFoldOpen\(lastFold \? `\$\{foldKey\(t\.id\)\}:\$\{lastFold\.id\}` : ""\), work = React\.useContext\(WorkCtx\), open = folded \|\| !work \|\| level !== "summary";/, "both hooks called on every render");
  assert.match(src, /const Fold = \(\{ k, label, quiet = false, children \}\) => \{\n  const open = useFoldOpen\(k\);/);
  // ...and the fold's open state is set by his click, in the render the click causes - heard from the native toggle (a task later), the line on
  // ACP followed the opened fold 75-90 ms late, saying the row's words under it (the judges' recording, 2026-11-18)
  const fold = src.slice(src.indexOf("const Fold = "), src.indexOf("// ONE RULE FOR EVERY FOLD"));
  assert.match(fold, /<summary onClick=\{\(e\) => \{ e\.preventDefault\(\); set\(!OPEN_FOLDS\.has\(k\)\); \}\}>/);
  assert.match(fold, /const set = \(o\) => \{ if \(o === OPEN_FOLDS\.has\(k\)\) return;[^\n]*FOLD_HEARD\.forEach/, "the click and the toggle agree on one state");
});


// ...ONLY A CARD THAT STOOD BEFORE HIS LINE (a walk, 2026-11-18): the agent's answer to his line raised a Post card twelve seconds later, and
// while his line was still the page's own it was drawn greyed "you wrote ... after it" - no button he ever saw lit
test("a card raised after his line is never greyed by it", () => {
  const pad = (n) => String(n).padStart(2, "0"), stamp = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  const typed = new Date(Date.now() - 20000), later = new Date(typed.getTime() + 12000), earlier = new Date(typed.getTime() - 30000);
  const card = (n, d) => ({ id: `r:${n}`, review: n, what: "action", status: "pending", at: stamp(d), was: { text: "Post it" }, aside: 'Not sent - you wrote "{line}" after it' });
  const read = { items: [mail, { ...answer, cards: [card(1, earlier), card(2, later)] }], pending: [], working: false };
  const got = withMine(read, [{ id: "l-2", kind: "line", text: "where is the button", at: typed, rest: true }]);
  assert.deepEqual(got.items[1].cards.map((c) => c.status), ["passed", "pending"]);
});

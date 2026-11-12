// THE TASK PAGE'S LAYOUT: Came from | the one chat (the owner, 2026-11-06: no Close out anywhere), and the work alone - full width - while an agent works
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { SECTIONS, homeSection, liveTerminal, soloTodo, cameFrom, agentStatus, agentWord, answeredOutside, reportLine, writeupAt, fromStatus, TAB_MOST, focusOf, fromLine, holderName, layoutOf, mainOf, nextInDrawer, sameWords, sectionFade, waitingOn, workPane } from "../src/taskLayout.js";
import { STAGE, sectionOf } from "../src/stages.js";
import { taskSource } from "./taskSource.mjs";

test("two columns at rest, the whole width while an agent works - coding or general, working or waiting on you", () => {
  assert.equal(layoutOf({ sessionView: false }), "columns");
  assert.equal(layoutOf({ sessionView: true }), "full");
  const src = taskSource();
  // the page's own "the session fills the page" decides it: a live session (term.alive - a terminal or a general agent's chat)
  assert.match(src, /const sessionView = \(liveSession \|\| chatKept\) && !peek;/);
  // ...and only a live session since 2026-10-25 (the owner: "keep the 2 columns for when agent is not working")
  assert.match(src, /const layout = layoutOf\(\{ sessionView \}\), wide = layout === "full";/);
  // ...the columns box steps aside but on a phone's stacked page; on the desk the THREE SECTIONS (the owner, 2026-10-27) are its children
  assert.match(src, /<Box ref=\{columnsBox\} data-tq-columns="" data-tq-layout=\{twoUp \? "sections" : sessionView \? "full" : stacked \? "stacked" : main\} sx=\{stacked \? COLUMNS : \{ display: "contents" \}\}>/);
  // ...the work column steps aside (display: contents) so the terminal stays a flex child of its section, sized as it always was
  assert.match(src, /sx=\{sessionView \|\| twoUp \? \{ display: "contents" \} : \{ minWidth: 0, display: "flex", flexDirection: "column", containerType: "inline-size",\s+\.\.\.\(main === "work" \? MAIN : settled \? \{ flex: "0 1 auto", minHeight: 0 \} : \{\}\) \}\}>/);
  // and on a phone's narrow body From is still a tab on the body's left edge over a live agent, opening a drawer laid OVER the main view (item
  // 6, the owner 2026-10-21; the tab 2026-10-26): absolutely placed, so the pane underneath is never resized; shut by the tab, its X, Escape
  // or a press outside. On the desk Came from is the first of the three sections instead
  assert.match(src, /\{fromDrawer && <Box component="button" type="button" ref=\{fromLineRef\} data-tq-from-line="" sx=\{DRAWER_TAB\(fromSide\)\}/);
  assert.match(src, /aria-expanded=\{fromSide\} aria-controls="tq-from-side" onClick=\{\(\) => setFromSide\(\(v\) => !v\)\}/);
  assert.match(src, /const fromDrawer = main === "work" && !twoUp;/);
  assert.match(src, /\{\(!fromDrawer \|\| fromSide\) && slot\("from",/);
  assert.match(src, /\.\.\.\(fromDrawer \? \{ \.\.\.card, px: 1\.5, py: 1\.25, \.\.\.FROM_SIDE \} : PHONE_FROM\(fromOpen \|\| solo\)\)/);
  assert.match(src, /const FROM_SIDE = \{ position: "absolute", top: 0, left: 0, bottom: 0,/);
  assert.match(src, /const \[fromSide, setFromSide\] = useState\(false\);/);
  assert.match(src, /if \(e\.key === "Escape"\) \{ e\.stopPropagation\(\); shut\(\)\?\.focus\(\); \}/);
  assert.match(src, /document\.addEventListener\("pointerdown", away, true\)/);
  assert.match(src, /useEffect\(\(\) => \{ if \(!sessionView\) setFromSide\(false\); \}, \[sessionView\]\);/);
  assert.doesNotMatch(src, /data-tq-work-tab|WORK_SIDE|workSide/, "the right drawer is gone: the closed sections are the tabs");
});

// THE WHOLE WIDTH IS A LIVE SESSION'S ALONE (the owner, 2026-10-25, reversing the 2026-10-22 fold for the states with no agent live): a
// finished, failed or closed agent is back in two columns - its Result the white focus on the right, Close out under it on the shade
test("the layout: two columns whenever no agent is live - a Result and a failure too; the whole width only while working or waiting", () => {
  const cases = [
    ["no agent at all", {}, "columns"],
    ["never started (handed or queued, nothing run)", { sessionView: false }, "columns"],
    ["working or waiting on you", { sessionView: true }, "full"],
    ["finished, stopped or saved with its Result", { result: true }, "columns"],
    ["failed, with its reason and Try again", { failed: true }, "columns"],
  ];
  for (const [what, page, want] of cases) assert.equal(layoutOf(page), want, what);
  // the focus: the Result (or the failed run) once an agent acted, the reply where that is the move; none while live
  assert.equal(focusOf({ result: true, pane: "reply" }), "agent");
  assert.equal(focusOf({ failed: true }), "agent");
  // ...but a draft or emails waiting for Send are the next move: Close out is white, the Result shaded above it (2026-10-27), and the stage is
  // close_out - the work view, so the main view does not change
  assert.equal(focusOf({ result: true, pane: "reply", owed: true }), "reply");
  assert.equal(focusOf({ result: true, pane: "agent", owed: true }), "reply");
  assert.equal(focusOf({ failed: true, owed: true }), "reply");
  assert.equal(focusOf({ live: true, owed: true }), null);
  assert.equal(focusOf({ waiting: true, owed: true }), "none");
  assert.equal(mainOf({ focus: focusOf({ result: true, owed: true }), drafted: true }), "work");
  assert.equal(focusOf({ pane: "reply" }), "reply");
  assert.equal(focusOf({ live: true, result: true }), null);
  // ...and the owner's answers (2026-10-25): a to-do or a goal whitens its own list, else the block with the ask's source - never
  // Send to agent; a task waiting on a person whitens nothing
  assert.equal(focusOf({ pane: "agent", list: true }), "list");
  assert.equal(focusOf({ pane: "agent" }), "source");
  assert.equal(focusOf({ pane: "", waiting: true }), "none");
  // the page reads its Result and its failure before the focus, and the From line, its sidebar and its X follow the layout
  const src = taskSource(), at = (re) => src.search(re);
  assert.ok(at(/const resultShown = /) < at(/const focus = focusOf\(/) && at(/const failedRun = /) < at(/const focus = focusOf\(/));
  // the "From" title and its X head only the sidebar (2026-10-22: the columns have no title over From)
  assert.match(src, /\{fromDrawer && <Box sx=\{\{ display: "flex", alignItems: "center" \}\}>\s+<Typography sx=\{\{ \.\.\.label, flex: 1 \}\}>From<\/Typography>\s+<IconButton size="small" aria-label="Close From" data-tq-from-close=""/);
  assert.match(src, /onClickCapture=\{stacked && !solo \? phoneFromTap : undefined\}/);
  // ...and no third section: what Close out held is the chat's cards (2026-11-06)
  assert.doesNotMatch(src, /slot\("close"|data-tq-closeout|closeOutRef/);
  // ...its record behind the Result's heading while the Result rests on its summary (2026-10-27: "click Result to see more")
  assert.match(src, /\{!sessionView && hasRecord && !resultRest && !chatPane && \(/);
  assert.match(src, /\{resultRest && !sessionView && !chatPane && <ResultSummary /);
});

// ...and the tab reads as a press (the owner, 2026-10-22: the line looked like plain grey text; 2026-10-26: "make it with arrow and more
// visible to pull out where it came from") - the whole edge, an arrow in a disc that turns while the drawer is out, a pointer, a tint on
// hover, a ring on focus. A native button, so Enter and Space press it. The three sections' closed tabs (2026-10-27) are the same kind of press
test("the tabs look pressable: an arrow, a pointer, a hover tint, a focus ring - the live drawer's and the sections' alike", () => {
  const src = taskSource(), tab = src.slice(src.indexOf("const DRAWER_TAB"), src.indexOf("\n\n", src.indexOf("const DRAWER_TAB")));
  assert.match(tab, /cursor: "pointer"/);
  assert.match(tab, /"&:hover": \{ bgcolor: lit \? "#46586a" : "var\(--tq-inset, #f3efe9\)" \}/);
  assert.match(tab, /"&:focus-visible": \{ outline: `2px solid \$\{lit \? INK : ACCENT\}`/);
  // ...lit, it is filled in the accent and peeks out once - never for a reader who asked for no motion
  assert.match(tab, /bgcolor: lit \? ACCENT :/);
  assert.match(tab, /"@media \(prefers-reduced-motion: reduce\)": \{ animation: "none" \}/);
  const left = src.slice(src.indexOf('data-tq-from-line=""'), src.indexOf("</Box></Box>}", src.indexOf('data-tq-from-line=""')));
  assert.match(left, /data-tq-from-chevron="">\{fromSide \? "‹" : "›"\}/);
  assert.match(left, /Came from/);
  // a section's closed tab: a native button, its words horizontal, a pointer, a hover tint, a focus ring; and the switch moves smoothly
  const sec = src.slice(src.indexOf("const SECTION_TAB"), src.indexOf("// ...the TAB each drawer folds to"));
  assert.match(sec, /appearance: "none", font: "inherit", cursor: "pointer"/);
  assert.doesNotMatch(sec, /writingMode/, "horizontal words");
  assert.match(sec, /"&:hover": \{ bgcolor: "var\(--tq-panel, #f8f6f2\)" \}/);
  assert.match(sec, /"&:focus-visible": \{ outline: `2px solid \$\{ACCENT\}`/);
  assert.match(src, /<Box component="button" type="button" data-tq-section-tab=\{sec\.key\}/);
  // ...its lines whole or not drawn, as many as the room holds and none skipped: never a fixed count, never squeezed to a sliver
  assert.match(sec, /"& \[data-tq-tab-line\]\[data-tq-unfit\]": \{ display: "none" \}/);
  assert.match(sec, /WebkitLineClamp: 3, WebkitBoxOrient: "vertical",\s+overflow: "hidden", flexShrink: 0/);
  assert.match(src, /const cut = ls\.findIndex\(.*\);\n\s+if \(cut >= 0\) ls\.slice\(cut\)/);
  assert.doesNotMatch(src, /newestFirst\(sources\.flatMap\(\(g\) => g\.msgs\)\)\.slice/, "every message goes to the tab");
  assert.match(src, /transition: `flex-grow \$\{SLOT_MS\}ms ease, flex-basis \$\{SLOT_MS\}ms ease`, "@media \(prefers-reduced-motion: reduce\)": \{ transition: "none" \}/);
});

// ONE MAIN VIEW (the owner, 2026-10-26): where the task is up to is the page, the other half its drawer; a phone keeps its stacked page
test("the main view follows where the task is up to: the work with Came from on the left, or the task with the work on the right", () => {
  assert.equal(mainOf({ sessionView: true }), "work", "a live agent");
  assert.equal(mainOf({ focus: "agent" }), "work", "its Result or its failure");
  assert.equal(mainOf({ focus: "reply", drafted: true }), "work", "Close out with a draft");
  // ...nothing drafted yet: the task is the page and the right tab is lit (the owner, 2026-10-26: "highlight the side bar")
  assert.equal(mainOf({ focus: "reply" }), "task", "a reply nothing has drafted");
  assert.equal(nextInDrawer({ main: "task", focus: "reply" }), true);
  assert.equal(nextInDrawer({ main: "task", focus: "source" }), true, "an ask nothing has worked: the agent is next");
  assert.equal(nextInDrawer({ main: "task", focus: "list" }), false, "a to-do's list is itself the move");
  assert.equal(nextInDrawer({ main: "work", focus: "agent" }), false, "Came from is context, never lit");
  // ...and ONLY the task's own next move lights it (the owner, 2026-10-26: "advisor should not light drawer for no reason"): the page's
  // focus, never a word of the Advisor's - the lit tab reads main and focus, and focus is read off the task alone
  assert.equal(nextInDrawer({ main: "task", focus: "list", advice: { verb: "reply" } }), false, "advice lights no tab");
  const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  // ...the right drawer and its lit tab went with the sections in a row (2026-10-27): the section the task is up to is its kind's and its
  // stage's (homeSection) - never the Advisor's (2026-11-06: its decision names no section)
  assert.match(page, /if \(mainHeld\.current\.key !== mainKey\) mainHeld\.current = \{ key: mainKey, main: mainNow, sec: solo \? "from" : writingUp \? "agent" : homeSection\(t\?\.Kind, taskStage, anyChat\) \};/);
  assert.match(page, /const taskStage = stageOf\(\{ focus: restFocus, drafted: replyHas, closed: /, "the stage reads the focus, never the advice");
  // ...the focus the task opens on - a section opened by hand changes neither the stage nor the main view (the overnight walk, 2026-10-27)
  const restLine = page.match(/const restFocus = focusOf\(\{[^;]*;/)?.[0];
  assert.ok(restLine, "the stage's focus is the unpicked pane's");
  assert.doesNotMatch(restLine.replace(/!openStage \? paneRest :/, ""), /openStage|advi|lit/i, "no pick and no advice in the stage's focus");
  const focusLine = page.match(/const focus = focusOf\(\{[^;]*\}\);/)?.[0];
  assert.ok(focusLine, "the page's focus is one focusOf");
  assert.doesNotMatch(focusLine, /advi|lit/i, "the focus reads no advice");
  assert.equal(mainOf({ focus: "list" }), "task", "a to-do or a goal's steps");
  assert.equal(mainOf({ focus: "source" }), "task", "an ask nothing has worked yet");
  assert.equal(mainOf({ focus: "none" }), "task", "a wait on a person");
  assert.equal(mainOf({ focus: "agent", stacked: true }), null, "a phone's stacked page");
  assert.equal(mainOf({ sessionView: true, stacked: true }), "work", "a live agent on a phone too");
});

test("the work column opens the agent or the reply - and what the task is for where the focus named the task", () => {
  assert.equal(workPane({ stage: "agent" }), "agent");
  assert.equal(workPane({ stage: "reply" }), "reply");
  assert.equal(workPane({ stage: "task", kind: "reply", hasSender: true }), "reply", "a reply to somebody opens the reply");
  assert.equal(workPane({ stage: "task", kind: "task", hasSender: true }), "reply");
  assert.equal(workPane({ stage: "task", kind: "coding", hasSender: true }), "agent", "an agent's task opens its plan and start");
  assert.equal(workPane({ stage: "task", kind: "general", hasSender: false }), "agent");
  assert.equal(workPane({ stage: "task", kind: "task", hasSender: false }), "agent", "nobody to answer: the agent half");
  assert.equal(workPane({ stage: "task", kind: "task", codeRun: true }), "reply", "a run of steps has no agent card");
});

// ...and an agent's Result stays open on a task nobody sent, where Stop and save opened an empty Close out under a Result folded to
// two lines (the owner, 2026-10-22: "since it gets crunched down you can not really see the agent report")
test("Stop and save on a task nobody sent keeps its Result the move; a reply, a close or a reply opened by hand make the reply the move", () => {
  assert.equal(workPane({ stage: "reply", kind: "coding", hasSender: false, result: true }), "agent", "nothing in the reply half: the Result");
  assert.equal(workPane({ stage: "reply", kind: "coding", hasSender: true, result: true }), "reply", "a reply is being drafted there");
  assert.equal(workPane({ stage: "reply", kind: "coding", hasSender: false, result: true, replyHas: true }), "reply", "a close, emails, a failed write-up");
  assert.equal(workPane({ stage: "reply", kind: "coding", hasSender: false, result: true, picked: true }), "reply", "the reply opened by hand");
  assert.equal(workPane({ stage: "reply", kind: "coding", hasSender: false, result: false }), "reply", "no Result: nothing to show instead");
});

test("a write-up under way is one line under the Result; one that failed is a card in the chat with its Try again", () => {
  const pending = { state: "pending", stage: "report" }, failed = { state: "failed", error: "no screen" };
  assert.equal(writeupAt(pending), "result");
  assert.equal(writeupAt(failed), "chat");
  assert.equal(writeupAt(null), null);
  const src = taskSource();
  // ...and no reply pill and no "Nobody sent this one" advice anywhere: the header's pill says where it stands (2026-10-25)
  assert.doesNotMatch(src, /<LifecycleChip kind="reply"|Nobody sent this one|CLOSE_BY_HAND/);
  assert.match(src, /const upAt = writeupAt\(writeup\), upFailed = upAt === "chat";/);
  assert.match(src, /\{upFailed && <WriteupBlock/);
  assert.match(src, /const lineAt = upAt !== "result" \? null : shows\("agent"\) && !sessionView && hasRecord && !resultRest && !chatPane \? "record" : "top";/);
  assert.equal((src.match(/<WriteupLine /g) || []).length, 2, "two spots, one lineAt: the line is drawn once");
  assert.match(src, /\{lineAt === "top" && <WriteupLine view=\{writeup\} hasReply=\{!!replyMessage\} \/>\}/);
  assert.match(src, /\{lineAt === "record" && <WriteupLine view=\{writeup\} hasReply=\{!!replyMessage\} \/>\}/);
  assert.doesNotMatch(src, /Closing the session and writing up what is on screen — the agent is not asked anything\.\s*<\/Typography>\s*\) : workspaceMode === "live" && peek/,
    "the third hint line over the write-up is gone");
});

test("From folds to who and how many", () => {
  assert.equal(fromLine({ sender: { FromName: "Gail Moreno", Channel: "email" }, count: 3 }), "Gail Moreno · 3 messages");
  assert.equal(fromLine({ sender: { FromEmail: "gail@northwind.example" }, count: 1 }), "gail@northwind.example · 1 message");
  assert.equal(fromLine({ sender: { Channel: "whatsapp" }, count: 8 }), "WhatsApp · 8 messages");
  assert.equal(fromLine({ workflow: { title: "Nightly check" } }), "Routine · Nightly check");
  assert.equal(fromLine({ made: "TQ-0007 · made by you 1h ago" }), "TQ-0007 · made by you 1h ago");
});

// FROM LISTS MANY ITEMS, NEWEST ON TOP: a burst of chat lines, a thread with your replies in it - the latest few, then "Show N older"
test("From reads newest on top, the older ones folded behind Show N older", async () => {
  const { fromExpands, fromRows, groupConversations } = await import("../src/taskSources.js");
  const at = (h, m) => `2026-10-21 ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`;
  const burst = [["Ray Colton", 7, 58], ["Gail Moreno", 8, 2], ["Ray Colton", 8, 10], ["Gail Moreno", 8, 14], ["Ray Colton", 8, 15], ["Gail Moreno", 8, 21]]
    .map(([who, h, m], i) => ({ MessageId: i + 1, Channel: "whatsapp", SourceName: "Site ops", FromName: who, SentAt: at(h, m), BodyText: `line ${i + 1}` }));
  const [g] = groupConversations(burst);
  const rows = fromRows(g, 3);
  assert.deepEqual(rows.slice(0, 3).map((r) => r.m.MessageId), [6, 5, 4], "the newest three, newest first");
  assert.equal(rows[3].older, 3, "then how many older");
  assert.match(rows[3].names, /Ray Colton/);
  assert.equal(rows.length, 4, "the opening message is not pinned under a gap any more");
  assert.deepEqual(fromRows(g, 3, true).map((r) => r.m.MessageId), [6, 5, 4, 3, 2, 1], "Show older draws every one, still newest first");
  assert.equal(fromRows({ msgs: g.msgs.slice(0, 4) }, 3).length, 4, "one more than it keeps is drawn, never folded to 'Show 1 older'");
  assert.equal(fromExpands([g]), true);
  // an email thread with your reply in it reads in its order, your line among theirs
  const thread = groupConversations([
    { MessageId: 10, Channel: "email", ConversationId: "c1", Subject: "AP cutover", FromName: "Gail Moreno", SentAt: at(9, 12), BodyText: "Can you confirm?" },
    { MessageId: "review:3", Channel: "email", ConversationId: "c1", Subject: "AP cutover", FromName: "You", Direction: "out", Status: "context", SentAt: at(9, 40), BodyText: "Yes, Monday." },
    { MessageId: 11, Channel: "email", ConversationId: "c1", Subject: "RE: AP cutover", FromName: "Gail Moreno", SentAt: at(10, 5), BodyText: "Thanks!" }]);
  assert.equal(thread.length, 1, "one thread");
  assert.deepEqual(fromRows(thread[0]).map((r) => r.m.who), ["Gail Moreno", "You", "Gail Moreno"]);
  assert.equal(fromExpands(thread), false, "three letters: nothing folded");
});

// THE TASK-VIEW CLEANUP (owner-approved 2026-10-25): the ask said once, and a task handed to a person opens on who it waits on
test("the ask is the message's own words only when they are the same words, spacing aside", () => {
  assert.ok(sameWords("Are we still on\nfor Thursday?","Are we still on  for Thursday? "));
  assert.ok(!sameWords("Confirm the Thursday cutover", "Are we still on for Thursday?"));
  assert.ok(!sameWords("", ""), "no ask is not the body");
});

test("a task waiting on a person says who and when it was due", () => {
  const now = new Date(2026, 9, 25, 9, 0);
  const task = { Status: "waiting", Assignee: "person:erin.blake@northwind.example", DueAt: "2026-10-23" };
  assert.equal(holderName("erin.blake@northwind.example"), "Erin Blake");
  assert.match(waitingOn({ task, now }).line, /^Waiting on Erin Blake\. Due Oct 23, 2 days late\.$/);
  // ...the name their own mail signs with, where the task has it
  assert.equal(waitingOn({ task, now, messages: [{ FromEmail: "Erin.Blake@northwind.example", FromName: "Erin B." }] }).name, "Erin B.");
  assert.equal(waitingOn({ task: { ...task, DueAt: "" }, now }).line, "Waiting on Erin Blake.");
  assert.equal(waitingOn({ task: { ...task, DueAt: "2026-10-30" }, now }).line, "Waiting on Erin Blake. Due Oct 30.");
  assert.equal(waitingOn({ task: { ...task, Status: "open" }, now }), null, "not waiting");
  assert.equal(waitingOn({ task: { ...task, Assignee: "agent:coding" }, now }), null, "an agent is not a person it waits on");
});

// THE SECTIONS' CLOSED TABS (the owner, 2026-10-27): the flow's order, and a few short lines each - at the top who and what, at the
// foot (a book's spine) the one status line
test("the two sections come in the flow's order, and each closed tab says where it stands", () => {
  assert.deepEqual(SECTIONS.map((s) => `${s.n} · ${s.name}`), ["1 · Came from", "2 · Agent"]);
  // ...at a glance: on what and how many, then every message newest first - who and a short line each; the tab draws as many as fit
  assert.deepEqual(fromStatus({ channel: "WhatsApp", count: 5, sorted: "Sorted: a reply to send · regular priority",
    msgs: [{ who: "Erin Blake", words: "So let's\nbuild one." }, { who: "You", words: "A link" }, { who: "Erin Blake", words: "Look" }, { who: "Ray Colton", words: "Old" }] }),
    { lines: ["WhatsApp · 5 messages", "Erin Blake: “So let's build one.”", "You: “A link”", "Erin Blake: “Look”", "Ray Colton: “Old”"], foot: "✓ Sorted: a reply to send · regular priority" });
  assert.deepEqual(fromStatus({ workflow: { title: "Nightly check" } }).lines, ["Routine · Nightly check"], "a workflow run has no sender");
  // ...and a long chat gives the spine no more lines than it can hold: the newest, the rest never drawn to be measured and hidden (2026-11-01)
  const chat = fromStatus({ channel: "WhatsApp", count: 1500, msgs: Array.from({ length: 1500 }, (_, i) => ({ who: "Gail Moreno", words: `line ${1500 - i}` })) });
  assert.equal(chat.lines.length, 1 + TAB_MOST); assert.equal(chat.lines[1], "Gail Moreno: “line 1500”");
  // ...an email's first line is its sender, never the owner's own mailbox it came into; a chat's is its room (the overnight run, 2026-11-03)
  assert.equal(cameFrom({ Channel: "email", SourceName: "alex@northwind.example", FromName: "Gail Moreno", FromEmail: "gail@northwind.example" }), "Gail Moreno");
  assert.equal(cameFrom({ Channel: "email", SourceName: "alex@northwind.example", FromEmail: "gail@northwind.example" }), "gail@northwind.example");
  assert.equal(cameFrom({ Channel: "whatsapp", SourceName: "Finance team", FromName: "Ray Colton" }), "Finance team");
  assert.match(fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8"), /channel: cameIn \? cameFrom\(cameIn\) \|\| channelName\(cameIn\.Channel\)/);
  assert.equal(agentWord({}), "not started");
  assert.equal(agentWord({ live: true, waiting: true }), "needs you");
  assert.equal(agentWord({ failed: true, result: true }), "failed");
  assert.equal(agentWord({ result: true }), "finished");
  // ...and a run the owner stopped (Stop and save, a restart) reads stopped with its result shown, never finished (2026-11-03)
  assert.equal(agentWord({ stopped: true, result: true }), "stopped");
  const tp = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(tp, /const stoppedRun = !term\?\.alive && \(detail\?\.runEnded === "stopped" \|\| \["saved", "interrupted"\]\.includes\(detail\?\.agentStory\?\.kind\)\);/);
  assert.match(tp, /failed: failedRun, stopped: stoppedRun \|\| agentState === AGENT\.stopped,/);
  assert.deepEqual(agentStatus({ profile: "assistant", word: "finished", said: "Wrote a one-page plan.", made: "Plan for a first box" }),
    { lines: ["assistant · finished", "Wrote a one-page plan.", "Made: Plan for a first box"], foot: "✓ Done" });
  assert.deepEqual(agentStatus({}), { lines: ["not started"], foot: "" });
});

// the state matrix (2026-10-28): the Agent tab read "AGENT REPORT" - the report's marker, not what it said
test("a report's line is its Summary, never its AGENT REPORT marker", () => {
  assert.equal(reportLine("AGENT REPORT\nDetermination: Ray has it.\nActions: Read the sheet.\nSummary: Ray has the code."), "Ray has the code.");
  assert.equal(reportLine("AGENT REPORT\nDetermination: Ray has it."), "Ray has it.");
  assert.equal(reportLine("Looked at the sheet."), "Looked at the sheet.");
  assert.equal(reportLine(""), "");
  // a first line ending on a colon carries the line it opens - never "It says:" and nothing (the email walk, 2026-10-29)
  assert.equal(reportLine("AGENT REPORT\nThe vendor page says:\nRegistration closes Friday."), "The vendor page says: Registration closes Friday.");
  assert.equal(reportLine("Summary: It says:"), "Summary: It says:".replace(/^Summary:\s*/, ""));
});

// ANSWERED OUTSIDE TASKUARY (the owner, 2026-10-29): Mark done is filled for it, on the task's one row - the move names no section of the
// page (2026-11-06), so where the task opens is its kind's and stage's alone
// ...and the Agent's tab says its own state, no Advisor's next move (the owner, 2026-11-09: "assistant/advisor should only be on rail")
test("the task's own move fills a button and names no section; the Agent's tab says only its state", () => {
  assert.equal(agentStatus({ word: "finished", advisor: "Mark done" }).foot, "✓ Done", "an Advisor's word handed in is said nowhere");
  assert.equal(agentStatus({ word: "not started" }).foot, "");
  const src = taskSource();
  assert.doesNotMatch(src, /sectionHere|adviceIn|advisorAt|advisedHeld/);
  assert.doesNotMatch(src, /advisor: |warn\?\.advice/);
});

test("the chat knows the owner answered outside Taskuary: its Draft reply is not the lit move", () => {
  const ins = [1, 2].map((i) => ({ MessageId: i, Direction: "in", Status: "routed", FromName: "Erin Blake", SentAt: `2026-10-29 11:${i}0:00` }));
  const own = { MessageId: 3, Direction: "out", Status: "context", FromName: "You", Channel: "teams", SourceName: "Teams", SentAt: "2026-10-29 12:10:00" };
  assert.equal(answeredOutside({ messages: [...ins, own], outside: [own] }), own);
  assert.equal(answeredOutside({ messages: [...ins, own], outside: [own], pending: true }), null, "a draft waiting is a decision nobody took");
  const again = { ...ins[0], MessageId: 4, SentAt: "2026-10-29 12:30:00" };
  assert.equal(answeredOutside({ messages: [...ins, own, again], outside: [own] }), null, "she wrote again after it");
  const sentHere = { MessageId: "review:9", ReviewSent: true, Direction: "out", SentAt: "2026-10-29 12:20:00" };
  assert.equal(answeredOutside({ messages: [...ins, own, sentHere], outside: [own] }), null, "a reply sent from here since is not outside");
  assert.equal(answeredOutside({ messages: ins, outside: [] }), null);
  // ...and its Draft reply is not the lit move there: the empty draft box with its filled Draft with AI is not drawn, the reply button is outlined
  const src = taskSource();
  assert.match(src, /&& !writeup && !outside/);
  assert.match(src, /variant=\{outside \? "outlined" : "contained"\}/);
});

// EVERY TASK IS CAME FROM AND ITS ONE CHAT (the owner, 2026-11-06, on a to-do still showing Close out: "i thought we removed this from everywhere?
// ... there should no longer be close out code anywhere"): general, reply, coding - its live terminal a toggle inside the chat - and a plain
// to-do, which opens on what came in; one no agent has touched is that section alone, the box at its foot
test("no task kind or state lays a Close out section: Came from and the chat, a to-do nobody started Came from alone", () => {
  assert.deepEqual(SECTIONS.map((s) => s.key), ["from", "agent"]);
  for (const kind of ["general", "reply", "coding", "task", "research", "", undefined])
    for (const stage of Object.keys(STAGE)) {
      const at = homeSection(kind, stage);
      assert.ok(SECTIONS.some((s) => s.key === at), `${kind} · ${stage} -> ${at}`);
      assert.equal(at, kind === "task" ? sectionOf(stage) : "agent", `${kind} · ${stage}: every kind but a to-do opens on its chat`);
    }
  assert.ok(Object.values(STAGE).every((s) => s.section !== "close" && s.key !== "close_out"), "no stage names Close out");
  assert.equal(homeSection("task", "todo"), "from", "a to-do opens on what came in");
  assert.equal(homeSection("task", "agent_result"), "agent", "...and on its chat once an agent has a Result on it");
  // ...a to-do nobody started is one section; once anything ran, or for any other kind, two
  assert.equal(soloTodo({ kind: "task" }), true);
  assert.equal(soloTodo({ kind: "task", started: true }), false);
  for (const kind of ["general", "reply", "coding", ""]) assert.equal(soloTodo({ kind }), false, kind);
  // ...a live CODING terminal is the toggle in its chat; a general agent's own live chat ("assistant" mode) is not one
  assert.equal(liveTerminal({ alive: true, mode: "pty" }), true);
  assert.equal(liveTerminal({ alive: true }), true);
  assert.equal(liveTerminal({ alive: true, mode: "assistant" }), false);
  assert.equal(liveTerminal({ alive: false, mode: "pty" }), false);
  assert.equal(liveTerminal(null), false);
  const src = taskSource();
  assert.match(src, /const home = !!t;/);
  assert.match(src, /secs = solo \? SECTIONS\.slice\(0, 1\) : SECTIONS;/);
  assert.match(src, /const slots = secs, slotKeys = slots\.map\(\(s\) => s\.key\);/);
  assert.match(src, /const workspaceMode = home && !wrapping \? "general" : agentWorkspaceMode/, "every task is always the chat");
  // ...ONE chat for every kind: the page never picks between two (the component reads its own source, chatStream.chatSource)
  assert.doesNotMatch(src, /<CodingChat |liveTerminal\(term\) \? </, "no coding/general branch picks the chat");
  assert.equal((src.match(/<GeneralWorkspace /g) || []).length, 1);
  assert.match(src, /next=\{chatCards\}/);
  // ...the to-do's box at the foot of Came from, the chat's cards over it, and no Agent slot beside it
  const from = src.slice(src.indexOf('slot("from",'), src.indexOf("THE WORK COLUMN"));
  assert.match(from, /\{solo && <Box data-tq-solo-box="" sx=\{\{ mt: "auto", position: "sticky", bottom: 0/);
  assert.match(from, /<NoAgentChat task=\{t\} reviews=\{detail\?\.reviews \|\| \[\]\} cards=\{chatCards\} closed=\{closedSaid\}/);
  assert.match(src, /\{!solo && slot\("agent", <Box data-tq-work=/);
  // ...the task's own moves ride the chat's strip
  assert.match(src, /function useTaskMoves\(sec\) \{/);
  assert.match(src, /close = sec === "agent";/);
});

// ONE RULE FOR EVERY KIND (the owner, 2026-11-08): any agent, turn or draft on a task opens it on its chat with Came from the thin arrow tab -
// a reply kept a spine that cut its message to three lines; only a task with nothing but what came in opens on Came from
test("every kind with a chat opens on it, Came from folded thin; one with none opens on Came from", () => {
  for (const kind of ["reply", "general", "coding", "task"]) {
    assert.equal(homeSection(kind, "to_reply", true), "agent", kind);
    assert.equal(homeSection(kind, "to_reply", false), "from", kind);
  }
  const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  // ...a coding job's as a general one's: a coding task no session had touched opened on Came from with no box (the side-by-side walk, 2026-11-11)
  assert.match(page, /const anyChat = !!term\?\.alive \|\| hasRecord \|\| \["general", "coding"\]\.includes\(t\?\.Kind\) \|\| \/\^agent:\/\.test\(String\(t\?\.Assignee \|\| ""\)\)/,
    "a task given to an agent - general or coding - opens on its chat before the agent says a word");
  assert.match(page, /const closedW = \(k\) => \(k === "from" \|\| \(sessionView && k !== "agent"\) \? MINI_W : tabW\(bodyW\)\);/);
});

// THE RAIL WALK (2026-11-12): every Next and row click drew the next task's header over an empty body for ~0.4s - the section's fade-in, meant
// for a switch, ran on its first draw too. The section an item is first drawn on draws at once; a switch after it fades; another item starts again.
test("a task's first section draws at once; only a switch fades its words in", () => {
  let m = sectionFade(null, null, 7);                 // ...the page's first frame, before its width is known: no section yet
  m = sectionFade(m, "agent", 7); assert.equal(m.moved, false, "the section the task is first drawn on draws at once");
  m = sectionFade(m, "agent", 7); assert.equal(m.moved, false);
  m = sectionFade(m, "from", 7); assert.equal(m.moved, true, "a switch fades in");
  m = sectionFade(m, "agent", 7); assert.equal(m.moved, true, "...and so does the switch back");
  m = sectionFade(m, "from", 8); assert.equal(m.moved, false, "the next task (Next, a rail click) draws at once whatever it opens on");
  // ...an item that names where it opens: its stale section from the item before is no switch
  let r = sectionFade(null, "report", "k1", "report"); r = sectionFade(r, "agent", "k2", "report"); assert.equal(r.moved, false);
  r = sectionFade(r, "report", "k2", "report"); assert.equal(r.moved, false); r = sectionFade(r, "agent", "k2", "report"); assert.equal(r.moved, true);
  const page = taskSource();
  assert.match(page, /transition: open && fade \? `opacity 160ms ease \$\{SLOT_MS\}ms, visibility 0s` : "none",\s+\.\.\.\(open && fade \? \{ "@starting-style": \{ opacity: 0 \} \} : \{\}\),/);
  for (const k of ["from", "agent"]) assert.match(page, new RegExp(`SECTION\\(isOpen\\("${k}"\\), openW\\("${k}"\\), [^)]*fades\\)`), `the ${k} section reads the page's own fade`);
});

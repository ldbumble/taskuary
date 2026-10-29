// THE TASK PAGE'S LAYOUT (the redesign, owner-approved 2026-10-21): From | Work, and the work alone - full width - while an agent works
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { CLOSE_BY_HAND, SECTIONS, agentStatus, agentWord, reportLine, closeStatus, closeOut, fromStatus, focusOf, fromLine, holderName, layoutOf, mainOf, nextInDrawer, sameWords, waitingOn, workPane } from "../src/taskLayout.js";
import { taskSource } from "./taskSource.mjs";

test("two columns at rest, the whole width while an agent works - coding or general, working or waiting on you", () => {
  assert.equal(layoutOf({ sessionView: false }), "columns");
  assert.equal(layoutOf({ sessionView: true }), "full");
  const src = taskSource();
  // the page's own "the session fills the page" decides it: a live session (term.alive - a terminal or a general agent's chat)
  assert.match(src, /const sessionView = liveSession && !peek;/);
  // ...and only a live session since 2026-10-25 (the owner: "keep the 2 columns for when agent is not working")
  assert.match(src, /const layout = layoutOf\(\{ sessionView \}\), wide = layout === "full";/);
  // ...the columns box steps aside but on a phone's stacked page; on the desk the THREE SECTIONS (the owner, 2026-10-27) are its children
  assert.match(src, /<Box ref=\{columnsBox\} data-tq-columns="" data-tq-layout=\{threeUp \? "sections" : sessionView \? "full" : stacked \? "stacked" : main\} sx=\{stacked \? COLUMNS : \{ display: "contents" \}\}>/);
  // ...the work column steps aside (display: contents) so the terminal stays a flex child of its section, sized as it always was
  assert.match(src, /sx=\{sessionView \|\| threeUp \? \{ display: "contents" \} : \{ minWidth: 0, display: "flex", flexDirection: "column", containerType: "inline-size",\s+\.\.\.\(main === "work" \? MAIN : settled \? \{ flex: "0 1 auto", minHeight: 0 \} : \{\}\) \}\}>/);
  // and on a phone's narrow body From is still a tab on the body's left edge over a live agent, opening a drawer laid OVER the main view (item
  // 6, the owner 2026-10-21; the tab 2026-10-26): absolutely placed, so the pane underneath is never resized; shut by the tab, its X, Escape
  // or a press outside. On the desk Came from is the first of the three sections instead
  assert.match(src, /\{fromDrawer && <Box component="button" type="button" ref=\{fromLineRef\} data-tq-from-line="" sx=\{DRAWER_TAB\(fromSide\)\}/);
  assert.match(src, /aria-expanded=\{fromSide\} aria-controls="tq-from-side" onClick=\{\(\) => setFromSide\(\(v\) => !v\)\}/);
  assert.match(src, /const fromDrawer = main === "work" && !threeUp;/);
  assert.match(src, /\{\(!fromDrawer \|\| fromSide\) && slot\("from",/);
  assert.match(src, /\.\.\.\(fromDrawer \? \{ \.\.\.card, px: 1\.5, py: 1\.25, \.\.\.FROM_SIDE \} : PHONE_FROM\(fromOpen\)\)/);
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
  assert.match(src, /onClickCapture=\{stacked \? phoneFromTap : undefined\}/);
  // ...while what a finished agent offers stays where it was: Close out and its record are drawn whenever no session fills the page
  // ...(and in the three sections it is the third section, beside a live agent too as a slim tab - 2026-10-27)
  assert.match(src, /\{\(!sessionView \|\| threeUp\) && slot\("close", <Box ref=\{closeOutRef\} data-tq-closeout=""/);
  // ...its record behind the Result's heading while the Result rests on its summary (2026-10-27: "click Result to see more")
  assert.match(src, /\{!sessionView && hasRecord && !resultRest && \(/);
  assert.match(src, /\{resultRest && !sessionView && <ResultSummary /);
});

// ...and the tab reads as a press (the owner, 2026-10-22: the line looked like plain grey text; 2026-10-26: "make it with arrow and more
// visible to pull out where it came from") - the whole edge, an arrow in a disc that turns while the drawer is out, a pointer, a tint on
// hover, a ring on focus. A native button, so Enter and Space press it. The three sections' closed tabs (2026-10-27) are the same kind of press
test("the tabs look pressable: an arrow, a pointer, a hover tint, a focus ring - the live drawer's and the sections' alike", () => {
  const src = taskSource(), tab = src.slice(src.indexOf("const DRAWER_TAB"), src.indexOf("\n\n", src.indexOf("const DRAWER_TAB")));
  assert.match(tab, /cursor: "pointer"/);
  assert.match(tab, /"&:hover": \{ bgcolor: lit \? "#46586a" : "#f3efe9" \}/);
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
  assert.match(sec, /"&:hover": \{ bgcolor: "#f8f6f2" \}/);
  assert.match(sec, /"&:focus-visible": \{ outline: `2px solid \$\{ACCENT\}`/);
  assert.match(src, /<Box component="button" type="button" data-tq-section-tab=\{sec\.key\}/);
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
  // ...the right drawer and its lit tab went with the three sections (2026-10-27): the section the task is up to is the stage's (sectionOf)
  assert.match(page, /if \(mainHeld\.current\.key !== mainKey\) mainHeld\.current = \{ key: mainKey, main: mainNow, sec: sectionOf\(taskStage\) \};/);
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
test("Stop and save on a task nobody sent keeps its Result open; a reply, a close or a hand-picked Close out still opens Close out", () => {
  assert.equal(workPane({ stage: "reply", kind: "coding", hasSender: false, result: true }), "agent", "nothing in the reply half: the Result");
  assert.equal(workPane({ stage: "reply", kind: "coding", hasSender: true, result: true }), "reply", "a reply is being drafted there");
  assert.equal(workPane({ stage: "reply", kind: "coding", hasSender: false, result: true, replyHas: true }), "reply", "a close, emails, a failed write-up");
  assert.equal(workPane({ stage: "reply", kind: "coding", hasSender: false, result: true, picked: true }), "reply", "Close out opened by hand");
  assert.equal(workPane({ stage: "reply", kind: "coding", hasSender: false, result: false }), "reply", "no Result: nothing to show instead");
});

test("Close out under a Result on a task nobody sent: no 'Nobody sent this one', no reply pill, the write-up under the Result", () => {
  const pending = { state: "pending", stage: "report" }, failed = { state: "failed", error: "no screen" };
  assert.deepEqual(closeOut({ hasSender: false, result: true, writeup: pending }), { advice: false, chip: false, writeupAt: "result" });
  assert.deepEqual(closeOut({ hasSender: false, result: true }), { advice: false, chip: false, writeupAt: null });
  assert.equal(closeOut({ hasSender: false, result: true, writeup: failed }).writeupAt, "closeout", "a failure keeps its Try again in Close out");
  // ...a reply being drafted stands where the draft will land (the owner, 2026-10-21: "open the Close out right away")
  assert.deepEqual(closeOut({ hasSender: true, result: true, writeup: pending }), { advice: true, chip: true, writeupAt: "closeout" });
  // ...and an open task nobody sent, nothing done yet, keeps its advice
  assert.deepEqual(closeOut({ hasSender: false, result: false }), { advice: true, chip: true, writeupAt: null });
  assert.equal(CLOSE_BY_HAND, "Mark done closes it, or close it with a note.");
  const src = taskSource();
  assert.match(src, /\|\| \(co\.advice \? "Nobody sent this one[^"]*" : CLOSE_BY_HAND\)/);
  // ...and no reply pill on Close out at all now: the header's pill says it, once (the task-view cleanup, owner-approved 2026-10-25)
  assert.doesNotMatch(src, /<LifecycleChip kind="reply"/);
  assert.match(src, /pane === "reply" && co\.writeupAt === "closeout" && <WriteupBlock/);
  assert.match(src, /co\.writeupAt === "result" && <WriteupLine view=\{writeup\} \/>/);
  assert.doesNotMatch(src, /Closing the session and writing up what is on screen — the agent is not asked anything\.\s*<\/Typography>\s*\) : workspaceMode === "live" && peek/,
    "the third hint line over the write-up is gone");
});

test("From folds to who and how many", () => {
  assert.equal(fromLine({ sender: { FromName: "Gail Moreno", Channel: "email" }, count: 3 }), "Gail Moreno · 3 messages");
  assert.equal(fromLine({ sender: { FromEmail: "gail@northwind.example" }, count: 1 }), "gail@northwind.example · 1 message");
  assert.equal(fromLine({ sender: { Channel: "whatsapp" }, count: 8 }), "WhatsApp · 8 messages");
  assert.equal(fromLine({ workflow: { title: "Nightly check" } }), "Workflow · Nightly check");
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

// THE THREE SECTIONS' CLOSED TABS (the owner, 2026-10-27): the flow's order, and a few short lines each - at the top who and what, at the
// foot (a book's spine) the one status line
test("the three sections come in the flow's order, and each closed tab says where it stands", () => {
  assert.deepEqual(SECTIONS.map((s) => `${s.n} · ${s.name}`), ["1 · Came from", "2 · Agent", "3 · Close out"]);
  // ...at a glance: on what and how many, then the last messages - who and a short line each, three at most
  assert.deepEqual(fromStatus({ channel: "WhatsApp", count: 5, sorted: "Sorted: a reply to send · regular priority",
    msgs: [{ who: "Erin Blake", words: "So let's\nbuild one." }, { who: "You", words: "A link" }, { who: "Erin Blake", words: "Look" }, { who: "Ray Colton", words: "Old" }] }),
    { lines: ["WhatsApp · 5 messages", "Erin Blake: “So let's build one.”", "You: “A link”", "Erin Blake: “Look”"], foot: "✓ Sorted: a reply to send · regular priority" });
  assert.deepEqual(fromStatus({ workflow: { title: "Nightly check" } }).lines, ["Workflow · Nightly check"], "a workflow run has no sender");
  assert.equal(agentWord({}), "not started");
  assert.equal(agentWord({ live: true, waiting: true }), "needs you");
  assert.equal(agentWord({ failed: true, result: true }), "failed");
  assert.equal(agentWord({ result: true }), "finished");
  assert.deepEqual(agentStatus({ profile: "assistant", word: "finished", said: "Wrote a one-page plan.", made: "Plan for a first box", advisor: "Send" }),
    { lines: ["assistant · finished", "Wrote a one-page plan.", "Made: Plan for a first box"], foot: "✓ Done · Advisor: Send is next" });
  assert.deepEqual(agentStatus({}), { lines: ["not started"], foot: "" });
  assert.deepEqual(closeStatus({ to: "Erin Blake", where: "WhatsApp", draft: "On it.", waiting: true }).lines,
    ["Reply to Erin Blake in WhatsApp", "“On it.”", "Drafted · waiting for Send"]);
  assert.deepEqual(closeStatus({ to: "Erin Blake", owed: true }).lines, ["Reply to Erin Blake", "Not drafted yet"]);
  assert.deepEqual(closeStatus({ sent: true }).lines, ["Sent"]);
  assert.deepEqual(closeStatus({ to: "Erin Blake", draft: "On it.", sent: true, sentWhen: "6:21 PM" }).lines, ["Reply to Erin Blake", "“On it.”", "Sent 6:21 PM"]);
  assert.deepEqual(closeStatus({ emails: 2 }).lines, ["2 emails waiting for Send"]);
  assert.deepEqual(closeStatus({}).lines, ["Nothing owed"]);
  assert.deepEqual(closeStatus({ closed: true, note: "paid" }).lines, ["Closed · paid"]);
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

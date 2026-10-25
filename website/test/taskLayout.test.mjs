// THE TASK PAGE'S LAYOUT (the redesign, owner-approved 2026-10-21): From | Work, and the work alone - full width - while an agent works
import test from "node:test";
import assert from "node:assert/strict";
import { CLOSE_BY_HAND, closeOut, focusOf, fromLine, holderName, layoutOf, sameWords, waitingOn, workPane } from "../src/taskLayout.js";
import { taskSource } from "./taskSource.mjs";

test("two columns at rest, the whole width while an agent works - coding or general, working or waiting on you", () => {
  assert.equal(layoutOf({ sessionView: false }), "columns");
  assert.equal(layoutOf({ sessionView: true }), "full");
  const src = taskSource();
  // the page's own "the session fills the page" decides it: a live session (term.alive - a terminal or a general agent's chat)
  assert.match(src, /const sessionView = liveSession && !peek;/);
  // ...and only a live session since 2026-10-25 (the owner: "keep the 2 columns for when agent is not working")
  assert.match(src, /const layout = layoutOf\(\{ sessionView \}\), wide = layout === "full";/);
  assert.match(src, /<Box ref=\{columnsBox\} data-tq-columns="" data-tq-layout=\{layout\} sx=\{wide \? \{ display: "contents" \} : COLUMNS\}>/);
  // ...the work column steps aside (display: contents) so the terminal stays a flex child of the page, sized as it always was
  assert.match(src, /<Box ref=\{workBox\} data-tq-work="" sx=\{sessionView \? \{ display: "contents" \} : \{ minWidth: 0, display: "flex", flexDirection: "column", containerType: "inline-size", \.\.\.\(settled \? \{ flex: "0 1 auto", minHeight: 0 \} : \{\}\) \}\}>/);
  // and From is one line over it, which opens From as a sidebar laid OVER the agent's left edge (item 6, the owner 2026-10-21):
  // absolutely placed, so the pane underneath is never resized; closed by default, by the line, its X or Escape
  assert.match(src, /\{wide && <Box component="button" type="button" ref=\{fromLineRef\} data-tq-from-line=""\s+title=\{fromSide \? "Hide where this came from" : "Show where this came from"\}\s+aria-expanded=\{fromSide\} aria-controls="tq-from-side" onClick=\{\(\) => setFromSide\(\(v\) => !v\)\}/);
  assert.match(src, /\{\(!wide \|\| fromSide\) && \(/);
  assert.match(src, /\.\.\.\(wide \? \{ \.\.\.card, px: 1\.5, py: 1\.25, \.\.\.FROM_SIDE\(fromTop\) \} : PHONE_FROM\(fromOpen\)\)/);
  assert.match(src, /const FROM_SIDE = \(top\) => \(\{ position: "absolute", top, left: 0, bottom: 0,/);
  assert.match(src, /const \[fromSide, setFromSide\] = useState\(false\)/);
  assert.match(src, /if \(e\.key === "Escape"\) \{ e\.stopPropagation\(\); setFromSide\(false\);/);
  assert.match(src, /useEffect\(\(\) => \{ if \(!sessionView\) setFromSide\(false\); \}, \[sessionView\]\);/);
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
  // the focus: the Result (or the failed run) once an agent acted, else the open half - the reply for the rest; none while live
  assert.equal(focusOf({ result: true, pane: "reply" }), "agent");
  assert.equal(focusOf({ failed: true }), "agent");
  assert.equal(focusOf({ pane: "reply" }), "reply");
  assert.equal(focusOf({ pane: "" }), "reply", "a task waiting on a person: Close out");
  assert.equal(focusOf({ pane: "agent" }), "agent");
  assert.equal(focusOf({ live: true, result: true }), null);
  // the page reads its Result and its failure before the focus, and the From line, its sidebar and its X follow the layout
  const src = taskSource(), at = (re) => src.search(re);
  assert.ok(at(/const resultShown = /) < at(/const focus = focusOf\(/) && at(/const failedRun = /) < at(/const focus = focusOf\(/));
  // the "From" title and its X head only the sidebar (2026-10-22: the columns have no title over From)
  assert.match(src, /\{wide && <Box sx=\{\{ display: "flex", alignItems: "center" \}\}>\s+<Typography sx=\{\{ \.\.\.label, flex: 1 \}\}>From<\/Typography>\s+<IconButton size="small" aria-label="Close From" data-tq-from-close=""/);
  assert.match(src, /onClickCapture=\{wide \? undefined : phoneFromTap\}/);
  // ...while what a finished agent offers stays where it was: Close out and its record are drawn whenever no session fills the page
  assert.match(src, /\{!sessionView && <Box ref=\{closeOutRef\} data-tq-closeout=""/);
  assert.match(src, /\{!sessionView && hasRecord && \(/);
});

// ...and the line reads as a press (the owner, 2026-10-22: it looked like plain grey text) - a chevron after the words that turns while
// the sidebar is open, a pointer, a tint and an underline on hover. A native button, so Enter and Space press it.
test("the folded From line looks pressable: a chevron that turns, a pointer, a hover underline", () => {
  const src = taskSource(), at = src.indexOf('data-tq-from-line=""'), line = src.slice(at, src.indexOf("</Box></Box>}", at));
  assert.match(line, /cursor: "pointer"/);
  assert.match(line, /"&:hover": \{ color: INK, bgcolor: "#f4f1ec" \}/);
  assert.match(line, /"&:hover \[data-tq-from-words\]": \{ textDecoration: "underline"/);
  assert.match(line, /data-tq-from-chevron="" sx=\{[^}]*\}\}>\{fromSide \? "◂" : "▸"\}/);
  assert.ok(line.indexOf("data-tq-from-words") < line.indexOf("data-tq-from-chevron"), "the chevron comes after the words");
  assert.doesNotMatch(line, /data-tq-from-words="" sx=\{[^}]*flex: 1/, "the chevron sits right after the words, not pushed to the far edge");
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

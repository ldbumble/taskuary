// THE TASK PAGE'S LAYOUT (the redesign, owner-approved 2026-10-21): From | Work, and the work alone - full width - while an agent works
import test from "node:test";
import assert from "node:assert/strict";
import { fromLine, layoutOf, workPane } from "../src/taskLayout.js";
import { taskSource } from "./taskSource.mjs";

test("two columns at rest, the whole width while an agent works - coding or general, working or waiting on you", () => {
  assert.equal(layoutOf({ sessionView: false }), "columns");
  assert.equal(layoutOf({ sessionView: true }), "full");
  const src = taskSource();
  // the page's own "the session fills the page" decides it: a live session (term.alive - a terminal or a general agent's chat)
  assert.match(src, /const sessionView = liveSession && !peek;/);
  assert.match(src, /<Box data-tq-columns="" data-tq-layout=\{layoutOf\(\{ sessionView \}\)\} sx=\{sessionView \? \{ display: "contents" \} : COLUMNS\}>/);
  // ...the work column steps aside (display: contents) so the terminal stays a flex child of the page, sized as it always was
  assert.match(src, /<Box data-tq-work="" sx=\{sessionView \? \{ display: "contents" \} : \{ minWidth: 0, display: "flex", flexDirection: "column" \}\}>/);
  // and From is one line over it, which opens From as a sidebar laid OVER the agent's left edge (item 6, the owner 2026-10-21):
  // absolutely placed, so the pane underneath is never resized; closed by default, by the line, its X or Escape
  assert.match(src, /\{sessionView && <Box component="button" type="button" ref=\{fromLineRef\} data-tq-from-line="" title=\{fromLine\}\n\s+aria-expanded=\{fromSide\} aria-controls="tq-from-side" onClick=\{\(\) => setFromSide\(\(v\) => !v\)\}/);
  assert.match(src, /\{\(!sessionView \|\| fromSide\) && \(/);
  assert.match(src, /\.\.\.\(sessionView \? FROM_SIDE\(fromTop\) : PHONE_FROM\(fromOpen\)\)/);
  assert.match(src, /const FROM_SIDE = \(top\) => \(\{ position: "absolute", top, left: 0, bottom: 0,/);
  assert.match(src, /const \[fromSide, setFromSide\] = useState\(false\)/);
  assert.match(src, /if \(e\.key === "Escape"\) \{ e\.stopPropagation\(\); setFromSide\(false\);/);
  assert.match(src, /useEffect\(\(\) => \{ if \(!sessionView\) setFromSide\(false\); \}, \[sessionView\]\);/);
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

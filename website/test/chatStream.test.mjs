// A CODING TASK IS THE SAME ONE CHAT (the owner, 2026-11-06): one session told twice - as Claude's own log read into steps (sessionrecord), and as
// the ACP session/update notifications the same session sends over ACP (codingchat.record_update) - draws the SAME chat rows. Invented people.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { asUtc } from "../src/dates.js";
import { editHunks, headerOf, hunksOf, hunkText, langOf, numbered, parseUnified, tokens } from "../src/diffView.js";

const before = Array.from({ length: 20 }, (_, i) => `line ${i + 1}`);
const after = before.map((l) => (l === "line 12" ? "    total = a + tax" : l));
const text = (ls) => `${ls.join("\n")}\n`;
// Claude's structuredPatch for the same edit, as its log keeps it (toolUseResult)
const patch = { oldStart: 9, oldLines: 7, newStart: 9, newLines: 7,
  lines: [" line 9", " line 10", " line 11", "-line 12", "+    total = a + tax", " line 13", " line 14", " line 15"] };

const LOG = [
  { k: "brief", text: "TASKUARY: work TQ-0042 ...", at: "2026-11-06 09:00:00" },
  { k: "tool", name: "Read", args: { file_path: "C:/work/ledger/store.py" }, text: "C:/work/ledger/store.py", at: "2026-11-06 09:00:05" },
  { k: "tool", name: "Bash", args: { command: "pytest -q tests" }, text: "pytest -q tests", at: "2026-11-06 09:00:06" },
  { k: "tool", name: "Edit", args: { file_path: "C:/work/ledger/budget.py" }, file: "C:/work/ledger/budget.py", edit: { hunks: [patch] }, at: "2026-11-06 09:00:08" },
  { k: "said", text: "Fixed: the total now adds the tax line.", at: "2026-11-06 09:00:12" },
  { k: "you", text: "Run the whole suite too.", at: "2026-11-06 09:01:00" },
  { k: "tool", name: "Bash", args: { command: "pytest -q" }, text: "pytest -q", at: "2026-11-06 09:01:04" },
  { k: "said", text: "All 212 pass.", at: "2026-11-06 09:01:30" },
];
const chunks = (kind, t) => t.match(/.{1,7}/gs).map((x) => ({ sessionUpdate: kind, content: { type: "text", text: x } }));
const ACP = [
  { sessionUpdate: "user_message_chunk", content: { type: "text", text: "TASKUARY: work TQ-0042 ..." }, _meta: { taskuary: "brief" } },
  { sessionUpdate: "tool_call", toolCallId: "a", kind: "read", title: "Read store.py", status: "pending", locations: [{ path: "C:/work/ledger/store.py" }] },
  { sessionUpdate: "tool_call_update", toolCallId: "a", status: "completed" },
  { sessionUpdate: "tool_call", toolCallId: "b", kind: "execute", title: "pytest", rawInput: { command: "pytest -q tests" } },
  { sessionUpdate: "tool_call_update", toolCallId: "b", status: "completed", content: [{ type: "content", content: { type: "text", text: "3 passed" } }] },
  { sessionUpdate: "tool_call", toolCallId: "c", kind: "edit", title: "Edit budget.py", locations: [{ path: "C:/work/ledger/budget.py" }] },
  { sessionUpdate: "tool_call_update", toolCallId: "c", status: "completed",
    content: [{ type: "diff", path: "C:/work/ledger/budget.py", oldText: text(before), newText: text(after) }] },
  ...chunks("agent_message_chunk", "Fixed: the total now adds the tax line."),
  { sessionUpdate: "user_message_chunk", content: { type: "text", text: "Run the whole suite too." } },
  { sessionUpdate: "tool_call", toolCallId: "d", kind: "execute", rawInput: { command: "pytest -q" } },
  ...chunks("agent_message_chunk", "All 212 pass."),
];
const ses = (more) => ({ sid: "s1", cli: "claude", at: "2026-11-06 09:00:00", ...more });
// the rows a person reads: ids, stamps and step names aside (an ACP session has no per-step clock; its steps are named by update, a log's by step)
const shape = (rows) => rows.map(({ id, at, steps, ended, ...r }) => r);
// ...and a command's output, which only ACP hands over (a log keeps the command alone)
const noOutput = (rows) => rows.map((r) => (r.parts ? { ...r, parts: r.parts.map((p) => (p.steps ? { ...p, steps: p.steps.map(({ detail, id, ...s }) => s) } : p)) } : r));









// ── the viewer ───────────────────────────────────────────────────────────────────────────────────
test("two whole files diff into git's own hunk, numbered as git numbers it", () => {
  const [h] = hunksOf(text(before), text(after));
  assert.deepEqual(h, patch);
  assert.equal(headerOf(h), "@@ -9,7 +9,7 @@");
  assert.deepEqual(hunksOf("", "a\nb\n").map(headerOf), ["@@ -0,0 +1,2 @@"]);
  const rows = numbered(h);
  assert.deepEqual(rows.slice(2, 5).map((r) => [r.op, r.old, r.new]), [[" ", 11, 11], ["-", 12, null], ["+", null, 12]]);
});

test("a snippet's before/after is shown whole and unnumbered; a patch with no numbers names none", () => {
  const [h] = editHunks({ parts: [{ old: "total = a", new: "total = a + tax" }] });
  assert.deepEqual(h.lines, ["-total = a", "+total = a + tax"]);
  assert.equal(numbered(h)[0].old, null);
  assert.equal(numbered(editHunks({ patch: "@@ def total\n-a\n+b" })[0])[1].new, null);
});

test("a branch's whole diff reads back per file, each hunk with the text the revert matches", () => {
  const diff = ["diff --git a/budget.py b/budget.py", "index 1..2 100644", "--- a/budget.py", "+++ b/budget.py",
    "@@ -1,3 +1,3 @@", " a", "-b", "+B", " c", "@@ -20 +20 @@", "-t", "+T",
    "diff --git a/new.py b/new.py", "new file mode 100644", "--- /dev/null", "+++ b/new.py", "@@ -0,0 +1,2 @@", "+x", "+y", ""].join("\n");
  const files = parseUnified(diff);
  assert.deepEqual(files.map((f) => [f.path, f.plus, f.minus, f.hunks.length, f.added]), [["budget.py", 2, 2, 2, false], ["new.py", 2, 0, 1, true]]);
  assert.equal(hunkText(files[0].hunks[1]), "@@ -20 +20 @@\n-t\n+T");
  assert.deepEqual(numbered(files[0].hunks[1]).map((r) => [r.old, r.new]), [[20, null], [null, 20]]);
  assert.equal(files[1].hunks[0].lines.length, 2);            // the diff's last newline is no line of the file
});

test("the highlighter colours by language and keeps every character", () => {
  const line = "def total(a): return a + 'tax'  # why";
  const t = tokens(line, langOf("ledger/budget.py"));
  assert.equal(t.map((x) => x.s).join(""), line);
  assert.deepEqual(t.filter((x) => x.t).map((x) => [x.t, x.s.trim()]), [["kw", "def"], ["kw", "return"], ["str", "'tax'"], ["com", "# why"]]);
  assert.deepEqual(tokens("x", ""), [{ t: "", s: "x" }]);
});




// ── recorded ACP update sequences ────────────────────────────────────────────────────────────────
const say = (t, at) => ({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: t }, ...(at ? { _at: at } : {}) });
const BRIEF = { sessionUpdate: "user_message_chunk", content: { type: "text", text: "TASKUARY: work TQ-0042 ..." }, _meta: { taskuary: "brief" } };
const flat = (turn) => turn.parts.flatMap((p) => (p.type === "work" ? p.steps.map((s) => `${s.kind === "said" ? "said" : "step"}:${s.summary}:${s.status}`)
  : p.type === "said" ? [`said:${p.text}`] : [`${p.type}`]));




test("the general chat's ACP trace keeps the words where they were said: the answer takes only what came after the last call", async () => {
  const { stepsOf } = await import("../src/agentSteps.js");
  // the trace agents.ACPSteps writes for the same recorded sequence (tests/test_acp_steps_order.py)
  const trace = [{ type: "progress", name: "text", detail: "Running the suite." },
    { type: "tool_call", name: "Bash", detail: { tool_call_id: "t1", args: { command: "pytest -q" } } },
    { type: "progress", name: "text", detail: "Quick update: half of it passed." },
    { type: "tool_result", name: "t1", detail: { tool_call_id: "t1", result: "212 passed" } },
    { type: "progress", name: "text", detail: "All 212 pass." }];
  const live = stepsOf(trace, { keepStart: false }).map((s) => s.summary);
  assert.deepEqual(live, ["Running the suite.", "Ran pytest", "Quick update: half of it passed.", "All 212 pass."]);
  // ...filed: the answer leaves the trail, every earlier line stays where it stood
  assert.deepEqual(stepsOf(trace, { keepStart: false, answer: "All 212 pass." }).map((s) => s.summary), live.slice(0, 3));
});

// A TASK OPENS ON THE LAST THING (the owner, 2026-11-11: "task should open on last thing not randomly in middle"). A long thread from Gail
// Moreno, the agent at rest: the chat pinned its end on the first draw, then each of forty long messages measured itself and drew a "Show
// all" - 896px more, after the pin and before the pin's own scroll event. That event found the end far away, read it as the owner having
// moved off, and nothing followed the chat down again - not the late picture either.
test("the chat lets go of its end only for the owner's own scroll up, never for its own growth", async () => {
  const { heldAtEnd, AT_END } = await import("../src/chatStream.js");
  // the live order: pinned at 4763 of 5297+534, grown to 6193 before the event - the same top, 896 from the end, nobody touching it
  assert.equal(heldAtEnd(true, { top: 4763, was: 0, gap: 896, own: false }), true, "growth after the pin is not a move away");
  assert.equal(heldAtEnd(true, { top: 4763, was: 4763, gap: 1319, own: true }), true, "nor is growth while a key is down in the box: the top did not go up");
  assert.equal(heldAtEnd(true, { top: 0, was: 4763, gap: 5000, own: false }), true, "nor a top the page itself moved");
  assert.equal(heldAtEnd(true, { top: 4400, was: 4763, gap: 363, own: true }), false, "his wheel up lets go");
  assert.equal(heldAtEnd(false, { top: 4500, was: 4400, gap: 263, own: true }), false, "and part of the way back down is still away");
  assert.equal(heldAtEnd(false, { top: 4763, was: 4500, gap: AT_END - 1, own: true }), true, "back at the end takes it again");
  assert.equal(heldAtEnd(true, { top: 4740, was: 4763, gap: 23, own: true }), true, "a nudge within the end's reach stays held");
  const view = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(view, /const on = \(\) => \{ stick\.current = heldAtEnd\(stick\.current, \{ top: v\.scrollTop, was, gap: v\.scrollHeight - v\.scrollTop - v\.clientHeight, own:/);
  // ...and nothing else moves it (the card round, 2026-11-12: a lit Send under a later answer - the helper that keeps a lit move in view
  // "showed whole" the row cut by the chat's top edge, 11 px back from the end, each frame for a second and a half)
  assert.match(view, /className="tq-aui-viewport" autoScroll=\{false\} data-tq-follows-end=""/);
  const { unclip } = await import("../src/inView.js");
  let moved = 0; const chat = { hasAttribute: (n) => n === "data-tq-follows-end", getBoundingClientRect: () => ({ top: 0, left: 0, width: 400, height: 300, bottom: 300 }), scrollTo: () => { moved += 1; }, scrollTop: 72 };
  unclip(chat, { getBoundingClientRect: () => ({ top: 200, bottom: 230 }) });
  assert.equal(moved, 0, "a scroller that follows its own end is never unclipped");
  assert.match(view, /const ro = new ResizeObserver\(\(\) => \{ if \(stick\.current\) v\.scrollTop = v\.scrollHeight; \}\);/, "and any resize while held pins it");
  assert.doesNotMatch(view, /stick\.current = v\.scrollHeight - v\.scrollTop - v\.clientHeight < 56/, "where it stands alone no longer decides");
});

// the working dots stood 0px under the last line the turn had said (the owner, 2026-11-11: "give it a drop of space")
test("the working dots keep room over them wherever something of the turn stands above", () => {
  const css = fs.readFileSync(new URL("../src/generalWorkspace.css", import.meta.url), "utf8");
  assert.match(css, /\.tq-aui-agent-body > \* \+ \.tq-aui-thinking \{ margin-top: 10px; \}/);
});

// three messages of one working turn stood as consecutive lines, 0px between (the owner, 2026-11-11): each is its own block of words
// (TurnWorkView draws a `said` part as one Md), and a block's last paragraph carries no room under it
test("each message of a turn is a paragraph: a block of its words keeps room under it, at work and at rest, in a fold too", () => {
  const css = fs.readFileSync(new URL("../src/generalWorkspace.css", import.meta.url), "utf8"), md = fs.readFileSync(new URL("../src/md.jsx", import.meta.url), "utf8");
  const view = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(md, /<Box sx=\{sx\} className="tq-md">/, "every block of words is named");
  assert.match(view, /p\.type === "said" \? <Md key=\{p\.id\} text=\{p\.text\} \/>/, "and a message of a turn is one, a direct child of the turn's body");
  assert.match(css, /\.tq-aui-agent-body > \.tq-md:not\(:last-child\), \.tq-aui-working-fold > \.tq-md:not\(:last-child\) \{ margin-bottom: 6px; \}/);
  assert.match(md, /"& p": \{ m: 0, mb: 0\.75 \}/, "the room a paragraph has inside one message: 6px");
});

// A LONG CHAT'S FIRST PAINTED FRAME IS ITS END. Its lines measure themselves in the draw that mounts them and each grows a "Show all" - after
// the pane's own pin. The end was watched from an effect that ran after the paint, so a task opened by a rail click painted one frame 896px
// short (sampled after each paint, 2026-11-11)
test("the chat is pinned to its end before its first paint: the watch is a layout effect, and the pin runs again once the draw is whole", () => {
  const view = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(view, /React\.useLayoutEffect\(\(\) => \{\r?\n    const v = viewport\.current, el = inner\.current;/, "the resize watch is set before the paint");
  assert.match(view, /React\.useLayoutEffect\(\(\) => \{ const pin = \(\) => \{[^\n]*v\.scrollTop = v\.scrollHeight; \};\r?\n    pin\(\); queueMicrotask\(pin\); \}\);/);
});



// WHAT WAITS BY THE BOX, WHEN MANY DO (decided 2026-11-12): the newest lines and the count - the strip scrolled from the oldest, the line he had
// just typed out of sight under a dozen older ones; a line that failed to go in stays wherever it stands
test("the waiting strip shows the newest lines with the count, and a failed line wherever it stands", async () => {
  const { waitingShown, WAIT_SHOWN } = await import("../src/chatStream.js");
  const lines = Array.from({ length: 12 }, (_, i) => ({ id: `l${i}`, text: `line ${i}` }));
  assert.deepEqual(waitingShown(lines.slice(0, 3)).map((x) => x.id), ["l0", "l1", "l2"], "a few are all shown");
  assert.deepEqual(waitingShown(lines).map((x) => x.id), ["l8", "l9", "l10", "l11"]);
  assert.equal(WAIT_SHOWN, 4);
  lines[2].err = "the agent could not take it";
  assert.deepEqual(waitingShown(lines).map((x) => x.id), ["l2", "l8", "l9", "l10", "l11"]);
  // ...over the box his lines show the newest TWO, "+N more" over them (the owner, 2026-11-12; basicFlow.test.mjs)
  assert.deepEqual(waitingShown(lines.slice(3), 2).map((x) => x.id), ["l10", "l11"]);
  const view = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(view, /shown = waitingShown\(rows, 2\), more = rows\.length - shown\.length;/);
  assert.match(view, /\{more > 0 && <div className="tq-conv-pending-more" data-tq-pending-more="" data-tq-pending-ids=\{rows\.filter\(\(x\) => !shown\.includes\(x\)\)\.map\(\(x\) => x\.id\)\.join\(" "\)\}>\+\{more\} more<\/div>\}/);
  assert.match(view, /\{shown\.map\(\(x\) =>/);
});

test("the agent's open question is drawn in the turn that asked it, never under whatever came after", async () => {
  const { askTurn } = await import("../src/chatStream.js");
  const items = [{ id: "m:1", kind: "arrival" }, { id: "t:m:1:0", kind: "turn" }, { id: "m:2", kind: "arrival" }, { id: "t:m:2:0", kind: "turn" }];
  // recorded 2026-11-13: asked in the first turn, still open after the turn a second mail woke - it stood under that one, at the chat's foot
  assert.equal(askTurn({ request_id: "q1", text: "Which city?", turn: "t:m:1:0", said: true }, items), "t:m:1:0");
  // ...at the foot only while the list holds no such turn (a read behind), or names none
  assert.equal(askTurn({ request_id: "q1", turn: "t:m:9:0" }, items), "");
  assert.equal(askTurn({ request_id: "q1" }, items), ""); assert.equal(askTurn(null, items), "");
});

test("the letters that wait for his Send are drawn at the end of the turn the list names, never above later words", async () => {
  const { lettersTurn } = await import("../src/chatStream.js");
  // the owner's live task, 2026-11-13: a turn left the reply's card, the turn that went on from it wrote a second letter - both stood over its words
  const items = [{ id: "l1", kind: "line" }, { id: "t:l1:0", kind: "turn", state: "done" }, { id: "t:l1:1", kind: "turn", state: "done" }];
  assert.equal(lettersTurn({ letters: "t:l1:1" }, items), "t:l1:1");
  // ...held back while that turn is at work, as its cards are; and where the list names none (or a turn not drawn yet), the page's own place
  assert.equal(lettersTurn({ letters: "t:l1:1" }, [...items.slice(0, 2), { ...items[2], state: "working" }]), "");
  assert.equal(lettersTurn({ letters: null }, items), ""); assert.equal(lettersTurn({ letters: "t:l9:0" }, items), ""); assert.equal(lettersTurn(null, items), "");
  // ...nor over a line he has just sent (recorded 2026-11-13: its Send stood lit above his new line until the list was read again)
  assert.equal(lettersTurn({ letters: "t:l1:1" }, [...items, { id: "l2", kind: "line" }]), "");
});

test("a chat paints a held list only if it was read a moment ago - an older one spins until its read lands", async () => {
  // the owner, 2026-11-13: a long task opened on messages from his last visit, the rest coming in after
  const { paintable, HELD_FOR } = await import("../src/chatStream.js");
  const now = 1_000_000, old = { _at: now - HELD_FOR - 1, items: [{ id: "a" }] }, recent = { _at: now - 2000, items: [{ id: "b" }] };
  assert.equal(paintable(old, null, now), null);                   // from his last visit: nothing is painted, the chat spins
  assert.equal(paintable(recent, null, now), recent);              // drawn again as its session starts: no blank beat
  assert.equal(paintable(old, recent, now), recent);               // read ahead for Next: painted
  assert.equal(paintable(null, null, now), null);
});

// WHAT IT WROTE OUT FOR HIM IS NEVER FOLDED WITH ITS STEPS (the owner, 2026-11-15: he asked for a query to review - the turn read "6 steps ▸" and
// "The SQL is ready for you to review", the query itself behind the fold): a message of the turn that holds a block stays in the turn
test("a block the agent wrote out on its way is not folded behind the steps", async () => {
  const { isMade } = await import("../src/chatStream.js");
  assert.ok(isMade("Here is the script:\n\n```sql\nUPDATE facilities SET fax = NULL WHERE id IN (14, 22, 31);\n```"));
  assert.ok(isMade("| id | fax |\n|---|---|\n| 14 | 555-0100 |"));
  assert.ok(!isMade("Let me look at the folder first.") && !isMade("I'll use `psql` for this.") && !isMade(""));
  const src = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /p\.type === "said" && \(!ended \|\| isMade\(p\.text\)\)/);
});

// A REPLY THE AGENT REWROTE, THEN SENT, KEEPS ITS SENT CARD (recorded 2026-11-15): the rewrite is the same review, so the list holds its earlier
// version ("Earlier draft - rewritten below") above its own card - and the earlier version, drawn first, claimed every card of that review
test("an earlier version of a draft never takes its review's own card", async () => {
  const { isPastCard, standing } = await import("../src/chatStream.js");
  const old = { id: "r:12:c18", review: 12, status: "superseded", was: { text: "Hi Erin, September came to..." } }, own = { id: "r:12", review: 12, status: "approved" };
  const gone = { id: "r:7", review: 7, status: "withdrawn", was: { text: "Hi Gail" } };
  assert.ok(isPastCard(old) && isPastCard(gone) && !isPastCard(own) && !isPastCard({ status: "superseded" }));
  const items = [{ kind: "turn", cards: [old] }, { kind: "arrival" }, { kind: "turn", cards: [own] }, { kind: "card", ...gone }];
  assert.deepEqual([...standing(items)], [12], "review 12 still has its own card; review 7 is only its record");
  const src = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /if \(isPastCard\(c\)\) \{ if \(!stands\.has\(c\.review\)\) nodes\.forEach/);
});

// NOTHING IT WROTE IS INVISIBLE (the owner, 2026-11-15): the agent decides what to show, and where it saved a file and never showed it, the
// write's own step stands open on what was written once the turn's steps are opened - as a terminal shows it. A shown text file copies whole
test("a file the agent wrote opens on its contents inside the steps, and a shown text file has Copy", async () => {
  const { editRow } = await import("../src/chatStream.js");
  const w = editRow({ name: "Write", file: "/x/scratch/outputs/TQ-0017/clear_columns.sql", edit: { parts: [{ old: "", new: "BEGIN;\nUPDATE facilities SET fax = NULL;\nCOMMIT;\n" }] } });
  assert.equal(w.wrote, true); assert.match(w.summary, /^Wrote clear_columns\.sql/);
  assert.equal(editRow({ name: "Edit", file: "a.py", edit: { parts: [{ old: "x = 1", new: "x = 2" }] } }).wrote, false);
  const src = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /\{\.\.\.\(chat && p\.wrote && p\.hunks\.length \? \{ open: true, "data-tq-wrote": "" \} : \{\}\)\}/);
  const pages = fs.readFileSync(new URL("../src/PublishedPages.jsx", import.meta.url), "utf8");
  assert.ok(pages.includes("export const isText = (p) =>") && pages.includes("plain"), "plain text is read as text wherever it came from");
  assert.match(pages, /\{p\.url && isText\(p\) && <CopyFile f=\{p\} \/>\}/);
});

test("a missing fact is one question: the reply not written yet waits under no open question", async () => {
  // recorded on the real CLI, 2026-11-15: the agent asked for the owner's car plate and under its question stood the empty reply it could not
  // write yet, captioned with the same question, over a greyed Send
  const { askedFirst } = await import("../src/chatStream.js");
  const empty = { Kind: "draft", Status: "pending", DraftText: "" }, written = { ...empty, DraftText: "Hi Gail, it is AB12 CDE. Alex" };
  assert.equal(askedFirst({ request_id: "q1", text: "What is the plate?" }, [empty]), true);
  assert.equal(askedFirst(null, [empty]), false);                                          // ...nothing asked: the card says why it is empty
  assert.equal(askedFirst({ request_id: "q1" }, [written]), false);                         // ...a reply with words is his to send
  assert.equal(askedFirst({ request_id: "q1" }, [empty, { Kind: "slot", Status: "pending", DraftText: "x" }]), false);   // ...emails wait with it
});

// A CARD HE SAID NO TO STAYS WHERE IT STOOD (the real-CLI walk, 2026-11-16: Don't send took the email off the chat, only "You dropped the email"
// was left - the basic flow's "no card gone from the canvas"): drawn greyed with its words, under "Not sent"
test("a card he said no to is drawn where it stood, with its words", async () => {
  const { isPastCard } = await import("../src/chatStream.js");
  assert.ok(isPastCard({ id: "r:9", review: 9, status: "rejected", was: { text: "Hi Erin, the open house moved" } }));
  const src = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /rejected: \(\) => "Not sent - you said don't send"/);
});

// A TURN AT WORK SHOWS ITS STEPS COUNTED, SHUT (the owner, 2026-11-17: "7 minutes this is all the agent did? and that little feedback?" - 19 steps
// stood behind three short lines): while it runs the turn draws the same quiet "n steps" fold a finished one has, over its words, closed
test("a turn at work draws its steps behind the quiet n-steps fold, as a finished one does", async () => {
  const src = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /if \(now\) \{\s*const shown = [^]*?<WorkFold k=\{`\$\{key\}:all`\} quiet parts=\{rest\}/);
});

// HIS LINE SHOWS WHAT HE SENT WITH IT (the owner, 2026-11-17: "the prompt box should show attachment of whatever goes into prompt like report,
// dashboard, routine, attached pdf"): a pill per file on his bubble, from the press (his own line, files kept) to the heard line (`files`)
test("his line draws a pill for every file he sent with it, from the press on", () => {
  const src = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /\(x\.files \|\| \[\]\)\.map\(\(f\) => <AttachChip key=\{f\} name=\{fileName\(f\)\}/);
  assert.match(src, /kind: "line", text: w, files: files\.map\(\(a\) => a\.path\)/);
});

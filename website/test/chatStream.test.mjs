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

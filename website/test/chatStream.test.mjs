// A CODING TASK IS THE SAME ONE CHAT (the owner, 2026-11-06): one session told twice - as Claude's own log read into steps (sessionrecord), and as
// the ACP session/update notifications the same session sends over ACP (codingchat.record_update) - draws the SAME chat rows. Invented people.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { editHunks, headerOf, hunksOf, hunkText, langOf, numbered, parseUnified, tokens } from "../src/diffView.js";

const before = Array.from({ length: 20 }, (_, i) => `line ${i + 1}`);
const after = before.map((l) => (l === "line 12" ? "    total = a + tax" : l));
const text = (ls) => `${ls.join("\n")}\n`;
// Claude's structuredPatch for the same edit, as its log keeps it (toolUseResult)
const patch = { oldStart: 9, oldLines: 7, newStart: 9, newLines: 7,
  lines: [" line 9", " line 10", " line 11", "-line 12", "+    total = a + tax", " line 13", " line 14", " line 15"] };


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


test("the general chat's ACP trace keeps the words where they were said: the answer takes only what came after the last call", async () => {
  const { stepsOf } = await import("../src/agentSteps.js");
  // the trace agents.ACPSteps writes for the same recorded sequence (tests/test_acp_steps_order.py)
  const trace = [{ type: "progress", name: "text", detail: "Running the suite." },
    { type: "tool_call", name: "Bash", detail: { tool_call_id: "t1", args: { command: "pytest -q" } } },
    { type: "progress", name: "text", detail: "Quick update: half of it passed." },
    { type: "tool_result", name: "t1", detail: { tool_call_id: "t1", result: "212 passed" } },
    { type: "progress", name: "text", detail: "All 212 pass." }];
  const live = stepsOf(trace, { keepStart: false }).map((s) => s.summary);
  assert.deepEqual(live, ["Running the suite.", "Ran pytest -q", "Quick update: half of it passed.", "All 212 pass."]);
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


test("a chat paints a held list only if it was read a moment ago - an older one spins until its read lands", async () => {
  // the owner, 2026-11-13: a long task opened on messages from his last visit, the rest coming in after
  const { paintable, HELD_FOR } = await import("../src/chatStream.js");
  const now = 1_000_000, old = { _at: now - HELD_FOR - 1, items: [{ id: "a" }] }, recent = { _at: now - 2000, items: [{ id: "b" }] };
  assert.equal(paintable(old, null, now), null);                   // from his last visit: nothing is painted, the chat spins
  assert.equal(paintable(recent, null, now), recent);              // drawn again as its session starts: no blank beat
  assert.equal(paintable(old, recent, now), recent);               // read ahead for Next: painted
  assert.equal(paintable(null, null, now), null);
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
  assert.match(src, /if \(isPastCard\(c\) && stands\.has\(c\.review\)\) return \[wasCard\(c, rv\(c\.review\)\)\];/);
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
// was left - the basic flow's "no card gone from the canvas"): drawn with its words, under what he pressed - "Not sent"
test("a card he said no to is drawn where it stood, with its words", async () => {
  const { isPastCard } = await import("../src/chatStream.js");
  assert.ok(isPastCard({ id: "r:9", review: 9, status: "rejected", was: { text: "Hi Erin, the open house moved" } }));
  const src = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /if \(isPastCard\(c\) && c\.status === "rejected"\) \{ if \(!stands\.has\(c\.review\)\) claim\(\); return \[<NotSent key=\{c\.id\} c=\{c\} \/>\]; \}/);
  assert.match(src, /<div className="tq-conv-past-head">\{c\.what === "action" \? "You said no to this" : "Not sent - you said don't send"\}<\/div>/);
});


test("his line keeps its words through the swap: placed by the server before it is filed, it never draws empty", async () => {
  const { withMine } = await import("../src/chatStream.js");
  const mine = [{ id: "l-9", kind: "line", text: "Post it to all three.", files: [], at: new Date(), rest: true }];
  const placed = { items: [{ id: "l-9", kind: "line", text: "", files: [] }, { id: "t:9", kind: "turn", state: "starting", steps: [], cards: [] }], pending: [], working: true };
  const got = withMine(placed, mine);
  assert.deepEqual(got.items.filter((x) => x.kind === "line").map((x) => [x.id, x.text]), [["l-9", "Post it to all three."]], "one line, its words, in the server's place");
  const filed = { ...placed, items: [{ ...placed.items[0], text: "Post it to all three." }, placed.items[1]] };
  assert.deepEqual(withMine(filed, mine).items.filter((x) => x.kind === "line").map((x) => x.text), ["Post it to all three."]);
});

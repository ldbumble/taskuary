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
  // ...filed, the same: the answer is its last row, and its filed copy is the server's to leave out (chatlog.read `tail`)
});

// A TASK OPENS ON THE LAST THING (the owner, 2026-11-11: "task should open on last thing not randomly in middle"). A long thread from Gail
// Moreno, the agent at rest: the chat pinned its end on the first draw, then each of forty long messages measured itself and drew a "Show
// all" - 896px more, after the pin and before the pin's own scroll event. That event found the end far away, read it as the owner having
// moved off, and nothing followed the chat down again - not the late picture either.
// Walk 17, recorded: Send on the first of two cards folded it to "✓ Sent" a beat before the second was drawn - the chat, held at its end,
// got 400 px shorter and then longer again, and the view flicked up to the turn's words and back down within 0.2 s.
test("at its end a card's fold and the card drawn under it are one move, never up and back down", async () => {
  const { shrinkHeld, SHRINK_HOLD } = await import("../src/chatStream.js");
  let tall = 0; const drawn = [];
  for (const h of [1720, 1320, 1745]) { const keep = shrinkHeld(true, tall, h); drawn.push(Math.max(h, keep)); if (!keep) tall = h; }
  assert.deepEqual(drawn, [1720, 1720, 1745], "the fold waits for what comes under it: the chat never got shorter under him");
  assert.equal(shrinkHeld(false, 1720, 1320), 0, "away from its end the row he reads holds his place instead (anchorOf)");
  assert.ok(SHRINK_HOLD >= 300 && SHRINK_HOLD <= 800, "a beat, not a gap left standing");
  const view = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(view, /keep = shrinkHeld\(stick\.current, tall, h\)/, "the chat's own observer keeps it");
});

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
  assert.match(view, /const ro = new ResizeObserver\(\(\) => \{[\s\S]{0,700}?\s+if \(stick\.current\) v\.scrollTop = endAt\(v, el\);/, "and any resize while held pins it");
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


// EVERY ROW KEEPS ITS KEY (the owner, 2026-11-23: adopt the open-source model - Zed, Toad and agent-shell key a row by the agent's own id): the
// turn's rows as the log serves them, read again after a call joins the run and after words come under it - every row and part keeps its id,
// so React patches it in place and nothing is drawn again from nothing (a run keyed by all its calls was a new row each time it grew; parts p0, p1)
test("a row and a part keep their keys as the turn grows", async () => {
  const { eventsOf, turnParts } = await import("../src/chatStream.js");
  const read = (id, f) => ({ id, k: "tool", name: "Read", args: { file_path: `C:/work/${f}` }, status: "completed" });
  const said = (id, t) => ({ id, k: "said", text: t });
  const ids = (steps) => turnParts(eventsOf(steps, true), { live: true }).map((p) => [p.type, p.id, (p.steps || []).map((s) => s.id)]);
  const one = [said("s:x:m:1", "Reading the sheets."), read("s:x:c1", "a.csv")];
  const two = [...one, read("s:x:c2", "b.csv")];
  const three = [...two, said("s:x:m:2", "Both read.")];
  assert.deepEqual(ids(one), [["said", "s:x:m:1", []], ["work", "s:x:c1", ["s:x:c1"]]]);
  assert.deepEqual(ids(two)[1].slice(0, 2), ["work", "s:x:c1"], "the run that grew is the same part");
  assert.deepEqual(ids(two)[1][2], ["s:x:c1"], "and the same row, keyed by its first call");
  assert.deepEqual(ids(three).map((p) => p[1]), ["s:x:m:1", "s:x:c1", "s:x:m:2"], "words under it are a part of their own, by their own id");
});


// THE WORDS STREAM INTO THEIR ROW, AND THE TURN'S END MOVES NOTHING (the owner, 2026-11-23: "the live layout IS the finished layout")
test("a pushed row patches its turn in place, and a turn lays out the same at work and filed", async () => {
  const { eventsOf, patchSteps, runsOf, turnParts } = await import("../src/chatStream.js");
  const said = (id, t) => ({ id, k: "said", text: t }), read = (id) => ({ id, k: "tool", name: "Read", args: { file_path: "C:/work/a.csv" }, status: "completed" });
  const list = { rev: 3, items: [{ id: "l-1", kind: "line" }, { id: "t:1", kind: "turn", state: "working", steps: [said("s:x:m:1", "Checking the")] }] };
  const pushed = [{ tid: 7, turn: "t:1", step: said("s:x:m:1", "Checking the sheet.") }, { tid: 7, turn: "t:1", step: read("s:x:c1") },
    { tid: 8, turn: "t:1", step: read("s:y:c9") }];
  const got = patchSteps(list, pushed, 7);
  assert.deepEqual(got.items[1].steps.map((s) => [s.id, s.text || s.name]), [["s:x:m:1", "Checking the sheet."], ["s:x:c1", "Read"]], "in place, then at the foot - another task's never");
  assert.equal(got.items[0], list.items[0], "what was not touched is the same object");
  assert.equal(patchSteps(list, [{ tid: 7, turn: "t:9", step: read("s:x:c2") }], 7), list, "a turn not in the list yet waits for the read");
  const steps = [said("s:x:m:1", "Checking the sheet."), read("s:x:c1"), read("s:x:c2"), said("s:x:m:2", "Done.")];
  const at = (live) => runsOf(turnParts(eventsOf(steps, live), { live })).map((r) => [r.id, !!r.fold]);
  assert.deepEqual(at(true), at(false), "the same folds, by the same keys, live and filed");
  assert.deepEqual(at(false), [["s:x:m:1", false], ["s:x:c1", true], ["s:x:m:2", false]], "words where they were said, the work between them one fold");
});


// THE AGENT'S OWN WORDS ARE THE ROW (the owner, 2026-11-23: adopt the open-source model): an ACP agent's call reads by its title, an icon by
// its kind and the files it named - never our reading of its command; Taskuary's own tools and a road that gives no title keep our words
test("a titled call is the agent's title, kind and files; our own tools and an untitled call keep our words", async () => {
  const { eventsOf, turnParts } = await import("../src/chatStream.js");
  const rows = (steps) => turnParts(eventsOf(steps, false)).flatMap((p) => p.steps || []);
  const [ls, rd, grep, own, plain] = rows([
    { id: "s:x:c1", k: "tool", name: "Bash", title: "`ls -la vendors`", tool_kind: "execute", args: { command: "ls -la vendors", description: "List vendors" }, status: "completed" },
    { id: "s:x:c2", k: "tool", name: "Read", title: "Read File", tool_kind: "read", paths: ["C:/work/ledger/budget.py"], args: { file_path: "C:/work/ledger/budget.py" }, status: "completed" },
    { id: "s:x:c3", k: "tool", name: "Grep", title: "grep -n \"total\" src", tool_kind: "search", args: { pattern: "total" }, status: "completed" },
    { id: "s:x:c4", k: "tool", name: "mcp__taskuary__my_task", title: "mcp__taskuary__my_task", tool_kind: "other", args: {}, status: "completed" },
    { id: "s:x:c5", k: "tool", name: "Bash", args: { command: "ls -la vendors", description: "List vendors" }, status: "completed" }]);
  // ...a title that is only its own command text says nothing of what it does (walk 16): read by our words, as a road with no title is
  assert.deepEqual([ls.summary, ls.kind], ["Listed the files in vendors", "list"], "a title that is its command reads by what the command did");
  assert.deepEqual([rd.summary, rd.kind, rd.chips], ["Read File", "read", ["budget.py"]], "the file it named beside a title that does not say it");
  assert.deepEqual([grep.summary, grep.kind], ['grep -n "total" src', "search"]);
  assert.notEqual(own.summary, "mcp__taskuary__my_task", "Taskuary's own tool in the product's words");
  assert.equal(plain.summary, "Listed the files in vendors", "a call with no title of the agent's: our words, as before");
  assert.equal(rows([{ id: "a", k: "tool", name: "Read", title: "Read a.ts", tool_kind: "read", args: {}, status: "completed" },
    { id: "b", k: "tool", name: "Read", title: "Read b.ts", tool_kind: "read", args: {}, status: "completed" }]).length, 2, "two titled reads are two rows");
});


// A PERMISSION ASKED IS ON ITS CALL'S ROW (the owner, 2026-11-23: action cards stay cards; "just permissions to push something" in the row)
test("a permission waiting on him is drawn on its call's row with the agent's option names, and its card only where no row names it", async () => {
  const { askOn, asksOff, eventsOf, turnParts } = await import("../src/chatStream.js");
  const p = { id: "p1", call: "toolu_7", options: [{ kind: "allow_once", label: "Allow once" }, { kind: "reject_once", label: "Reject" }] };
  const row = { id: "s:x:toolu_7", call: "toolu_7", k: "tool", name: "Bash", title: "git push origin main", tool_kind: "execute", args: { command: "git push origin main" },
    status: "pending", ask: [{ id: "allow", name: "Yes, push it", kind: "allow_once" }, { id: "no", name: "No", kind: "reject_once" }, { id: "always", name: "Always", kind: "allow_always" }] };
  const [step] = turnParts(eventsOf([row], true), { live: true })[0].steps;
  const asked = askOn(step, new Map([[p.call, p]]));
  assert.deepEqual(asked.options, [{ kind: "allow_once", label: "Yes, push it" }, { kind: "reject_once", label: "No" }], "the agent's names, only what the request offers (no Always for a push)");
  assert.equal(askOn(step, new Map()), null, "answered, nothing waits on the row");
  const list = [{ kind: "turn", id: "t:1", steps: [row] }];
  assert.deepEqual(asksOff([p, { id: "p2", call: "toolu_8", options: [] }, { id: "p3", options: [] }], list).map((x) => x.id), ["p2", "p3"]);
});

test("his no on a call's row is the row's record of it: not run, in his name - never 'nobody allowed it'", async () => {
  const { eventsOf } = await import("../src/chatStream.js");
  const row = { id: "s:x:toolu_7", call: "toolu_7", k: "tool", name: "Bash", args: { command: "git push origin main" } };
  const result = (s) => eventsOf([{ ...row, ...s }], false).find((e) => e.type === "tool_result").detail;
  assert.deepEqual([result({ status: "pending", answer: "reject_once" }), result({ status: "failed", answer: "reject_once" })].map((d) => [d.result, d.state]),
    [["Not run - you said no.", "refused"], ["Not run - you said no.", "refused"]]);
  assert.equal(result({ status: "completed", answer: "allow_once", output: "pushed" }).result, "pushed", "allowed, it reads as it ran");
});


// THE CALL'S OWN DIFF, AND A COMMAND'S OUTPUT AS IT COMES (the owner, 2026-11-23: Zed draws the agent's `diff` and a live terminal)
test("an edit row is the call's own diff, never one read off its arguments, and a running command shows its newest output", async () => {
  const { eventsOf, turnParts } = await import("../src/chatStream.js");
  const parts = (steps, live = false) => turnParts(eventsOf(steps, live), { live });
  const asked = { id: "s:x:c1", k: "tool", name: "Edit", args: { file_path: "C:/work/budget.py", old_string: "a = 1", new_string: "a = 2" }, status: "completed" };
  assert.ok(!parts([asked]).some((p) => p.type === "edit"), "its arguments are no diff: the row is the call, worded");
  const made = { id: "s:x:c2", k: "tool", name: "Edit", file: "C:/work/budget.py", edit: { whole: true, parts: [{ old: "a = 1\n", new: "a = 2\n" }] }, status: "completed" };
  const [edit] = parts([made]);
  assert.deepEqual([edit.type, edit.id, edit.summary], ["edit", "s:x:c2", "Edited budget.py (+1 −1)"]);
  const out = Array.from({ length: 30 }, (_, i) => `test_${i} PASSED`).join("\r\n");
  const run = { id: "s:x:c3", k: "tool", name: "Bash", args: { command: "pytest -q" }, status: "in_progress", output: out };
  const [step] = parts([run], true)[0].steps;
  assert.equal(step.status, "running");
  assert.deepEqual(step.tail.split("\n"), Array.from({ length: 8 }, (_, i) => `test_${22 + i} PASSED`), "its newest lines, behind its row (AgentStepRows)");
  const [ended] = parts([{ ...run, status: "completed" }])[0].steps;
  assert.ok(!ended.tail && ended.detail.includes("test_29 PASSED"), "once it ends, the whole of it, behind the same row");
});

// THE BROWSER PANE OPENS BESIDE THE CHAT (walk 12, recorded): the chat went from full width to a column, every line re-wrapped, the chat grew from
// 997 to 1502 px and what he was reading moved ~500 px down the screen, three times in one task. Away from its end, the row he reads stays put
test("a change of width keeps the row he was reading where it stood", async () => {
  const { anchorOf, anchorShift } = await import("../src/chatStream.js");
  let narrow = false;
  const view = { scrollTop: 450, clientHeight: 400, getBoundingClientRect: () => ({ top: 100 }) };
  const hs = [100, 100, 100, 100, 100, 100, 100, 100], h = () => (narrow ? 200 : 100);
  const rows = hs.map((_, i) => ({ isConnected: true, children: [], name: i,
    getBoundingClientRect: () => { const y = i * h(); return { top: 100 + y - view.scrollTop, bottom: 100 + y + h() - view.scrollTop, height: h() }; } }));
  const at = () => rows[4].getBoundingClientRect().top;
  const mark = anchorOf(view, { children: rows }), was = at();
  assert.equal(mark.el.name, 4, "the row at the top of the view");
  narrow = true;                                                              // ...the pane opens: every row twice as tall
  assert.notEqual(at(), was, "unheld, the row he read moves");
  view.scrollTop += anchorShift(view, mark);
  assert.equal(at(), was, "held, it stands where it stood");
  const gw = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(gw, /else \{ const d = anchorShift\(v, mark\); if \(Math\.abs\(d\) > 1\) v\.scrollTop \+= d; \}/);
});

// The card gallery, 2026-11-25: a view taller than the window was drawn a beat after its chat opened; held at its end, the chat went to the view's
// foot and its title was off the top. What is drawn under a reply at rest never carries that reply's top out of the view
test("held at its end, a chat at rest follows what is drawn under it no further than the top of its newest reply", async () => {
  const { endAt } = await import("../src/chatStream.js");
  const chat = (hs, live = false) => {
    const view = { scrollTop: 0, clientHeight: 400, scrollHeight: hs.reduce((a, b) => a + b, 0), getBoundingClientRect: () => ({ top: 60 }) };
    const tops = hs.map((_, i) => hs.slice(0, i).reduce((a, b) => a + b, 0));
    const rows = hs.map((_, i) => ({ parentElement: { closest: () => null }, hasAttribute: () => false, getBoundingClientRect: () => ({ top: 60 + tops[i] - view.scrollTop }) }));
    return { view, root: { querySelectorAll: () => rows, querySelector: () => (live ? {} : null) }, tops };
  };
  const view = chat([14, 900]);                                 // the reply's head at 14, its view drawn late: 900 tall in a 400 window
  assert.equal(endAt(view.view, view.root), 14, "the reply's top stays at the top of the view - never its foot");
  view.view.scrollTop = 300;                                    // ...he read on past its top: the end is followed, as it was
  assert.equal(endAt(view.view, view.root), 514);
  const working = chat([14, 900], true);
  assert.equal(endAt(working.view, working.root), 514, "a turn at work is followed to its last word");
  const short = chat([600, 300, 80]);
  assert.equal(endAt(short.view, short.root), short.view.scrollHeight - 400, "a short reply's top is past the end: the end");
  const gw = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(gw, /v\.scrollTop = v\.scrollHeight/, "every pin to the end goes by the one rule");
});

// A CHAT OPENS AT THE START OF ITS NEWEST REPLY (the owner, 2026-11-24): opened at its very bottom, a long answer was read from its last lines up
test("a chat opens with the top of its newest reply at the top of the view, unless that is past the end", async () => {
  const { openAt } = await import("../src/chatStream.js");
  // rows laid out top to bottom at the given heights, in a view 400 tall scrolled to `scrollTop`; `cards`: a turn's trailing card row
  const chat = (hs, cards = []) => {
    const view = { scrollTop: 0, clientHeight: 400, scrollHeight: hs.reduce((a, b) => a + b, 0), getBoundingClientRect: () => ({ top: 60 }) };
    const tops = hs.map((_, i) => hs.slice(0, i).reduce((a, b) => a + b, 0));
    const rows = hs.map((_, i) => ({ name: i, parentElement: { closest: () => null }, hasAttribute: (n) => n === "data-tq-row-cards" && cards.includes(i),
      getBoundingClientRect: () => ({ top: 60 + tops[i] - view.scrollTop }) }));
    return { view, root: { querySelectorAll: () => rows }, tops };
  };
  const long = chat([120, 80, 120, 900]);                       // his line, a reply, his line, a reply taller than the view
  long.view.scrollTop = long.view.scrollHeight - 400;           // ...wherever it stood before: the answer does not depend on it
  assert.equal(openAt(long.view, long.root), long.tops[3], "the newest reply's top, not the bottom");
  const short = chat([600, 300, 80]);                           // a short last reply: its top is past the end, so the end
  assert.equal(openAt(short.view, short.root), short.view.scrollHeight - 400);
  const fits = chat([100, 120]);
  assert.equal(openAt(fits.view, fits.root), 0, "a chat that fits does not move");
  const carded = chat([120, 700, 260], [2]);                    // a reply and the cards it set up under it
  assert.equal(openAt(carded.view, carded.root), carded.tops[1], "the reply's top, its cards under it");
  const nested = chat([120, 700]), inner = { parentElement: { closest: () => ({}) }, hasAttribute: () => false, getBoundingClientRect: () => ({ top: 9999 }) };
  nested.root.querySelectorAll = ((all) => () => [...all, inner])(nested.root.querySelectorAll());
  assert.equal(openAt(nested.view, nested.root), nested.tops[1], "a row inside a row is not the chat's newest");
});

test("a failed turn says its failure once: the error step the open chat patched in gives way to the turn's own line (walk 19)", async () => {
  const { turnSteps, turnParts, eventsOf } = await import("../src/chatStream.js");
  const err = { id: "e:1.1", k: "error", text: "No AI is connected - connect one on Connections → AI to run this task", status: "failed" };
  const failed = { kind: "turn", state: "failed", fail: "No AI is connected - connect one on Connections → AI to run this task.", steps: [err] };
  const rows = (t) => turnParts(eventsOf(turnSteps(t), false)).flatMap((p) => p.steps || []);
  assert.deepEqual(rows(failed), []);
  assert.equal(rows({ ...failed, fail: undefined, state: "done" }).length, 1, "a turn with no failed line keeps the step");
});

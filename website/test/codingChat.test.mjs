// A CODING TASK IS THE SAME ONE CHAT (the owner, 2026-11-06): one session told twice - as Claude's own log read into steps (sessionrecord), and as
// the ACP session/update notifications the same session sends over ACP (codingchat.record_update) - draws the SAME chat rows. Invented people.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { chatRows, stepsFromAcp } from "../src/codingChat.js";
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
// the rows a person reads: ids and stamps aside, an ACP session has no per-step clock
const shape = (rows) => rows.map(({ id, at, ...r }) => r);

test("a session's log and the same session over ACP draw the same chat rows", () => {
  const log = chatRows({ sessions: [ses({ source: "Claude Code log", steps: LOG })] });
  const acp = chatRows({ sessions: [ses({ source: "acp", updates: ACP })] });
  assert.deepEqual(shape(acp), shape(log));
  assert.deepEqual(log.map((r) => r.kind), ["turn", "you", "turn"]);
  const [first] = log;
  assert.deepEqual(first.parts.map((p) => p.type), ["work", "edit", "said"]);
  assert.deepEqual(first.parts[0].steps.map((s) => s.summary), ["Read store.py", "Ran pytest"]);
  assert.equal(first.parts[1].summary, "Edited budget.py (+1 −1)");
  assert.equal(first.answer, "Fixed: the total now adds the tax line.");
});

test("Taskuary's own brief is never drawn; the owner's typed line is, on its own row", () => {
  const rows = chatRows({ sessions: [ses({ steps: LOG })] });
  assert.ok(!JSON.stringify(rows).includes("TASKUARY: work"));
  assert.equal(rows[1].text, "Run the whole suite too.");
});

test("the mail that came in stands over the turn it woke, a burst as one row", () => {
  const mails = [{ who: "Erin Blake", words: "The budget skips tax.", channel: "email", at: "2026-11-06 08:58:00", joined: "2026-11-06 08:59:00" },
    { who: "Erin Blake", words: "Also the rounding.", channel: "email", at: "2026-11-06 08:59:30", joined: "2026-11-06 08:59:40" },
    { who: "Ray Colton", words: "Any news?", channel: "email", at: "2026-11-06 09:00:40", joined: "2026-11-06 09:00:40" }];
  const rows = chatRows({ sessions: [ses({ steps: LOG })], mails });
  assert.deepEqual(rows.map((r) => r.kind), ["mail", "turn", "mail", "you", "turn"]);
  assert.deepEqual(rows[0].mail.map((m) => m.words), ["The budget skips tax.", "Also the rounding."]);
  assert.equal(rows[2].mail[0].who, "Ray Colton");
});

test("a live session's newest turn is the one at work, its newest step still running", () => {
  const rows = chatRows({ sessions: [ses({ live: true, steps: LOG.slice(0, 7) })] });
  const turn = rows.at(-1);
  assert.equal(turn.running, true);
  assert.equal(turn.parts.at(-1).steps.at(-1).status, "running");
  assert.equal(rows[0].running, false);
});

test("a step saved before its arguments were kept still reads by its one line", () => {
  const rows = chatRows({ sessions: [ses({ steps: [{ k: "tool", name: "Read", text: "C:/work/ledger/store.py" }, { k: "tool", name: "Bash", text: "Run the tests", detail: "pytest -q" }]})] });
  // ...a command the agent described reads as what it was for, as in the general chat
  assert.deepEqual(rows[0].parts[0].steps.map((s) => s.summary), ["Read store.py", "Run the tests"]);
});

test("a codex patch and a write each read as their own row", () => {
  const rows = chatRows({ sessions: [ses({ steps: [
    { k: "tool", name: "apply_patch", file: "portal/app.js", edit: { patch: "@@\n-a\n+b\n+c" } },
    { k: "tool", name: "Write", file: "portal/new.js", args: { file_path: "portal/new.js" }, edit: { parts: [{ old: "", new: "x\ny\n" }] } }] })] });
  assert.deepEqual(rows[0].parts.map((p) => p.summary), ["Edited app.js (+2 −1)", "Wrote new.js (+2 −0)"]);
});

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

test("the coding chat's box types into the running CLI, or picks the session back up", () => {
  const src = fs.readFileSync(new URL("../src/CodingChat.jsx", import.meta.url), "utf8");
  assert.match(src, /\/api\/tasks\/\$\{task\.TaskId\}\/waitroom/);
  assert.match(src, /\/api\/tasks\/\$\{task\.TaskId\}\/continue-work/);
  assert.match(src, /\/api\/tasks\/\$\{tid\}\/coding-chat/);
});

test("over ACP each step keeps the moment it came in, and the plan is one checklist - the newest of its turn", () => {
  const ups = [
    { sessionUpdate: "user_message_chunk", content: { type: "text", text: "TASKUARY: work TQ-0042 ..." }, _meta: { taskuary: "brief" }, _at: "2026-11-06 09:00:00" },
    { sessionUpdate: "plan", entries: [{ content: "Read the ledger", status: "in_progress" }, { content: "Fix the tax line", status: "pending" }], _at: "2026-11-06 09:00:02" },
    { sessionUpdate: "tool_call", toolCallId: "a", kind: "read", title: "Read store.py", status: "completed", locations: [{ path: "C:/work/ledger/store.py" }], _at: "2026-11-06 09:00:03" },
    { sessionUpdate: "plan", entries: [{ content: "Read the ledger", status: "completed" }, { content: "Fix the tax line", status: "in_progress" }], _at: "2026-11-06 09:00:04" },
    { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "On the tax line now." }, _at: "2026-11-06 09:00:05" },
  ];
  assert.equal(stepsFromAcp(ups).find((s) => s.k === "tool").at, "2026-11-06 09:00:03");
  const [turn] = chatRows({ sessions: [{ sid: "s", source: "acp", at: "2026-11-06 08:59:00", updates: ups }] });
  assert.equal(turn.at, "2026-11-06 09:00:02");
  const plans = turn.parts.filter((p) => p.type === "plan");
  assert.equal(plans.length, 1);
  assert.deepEqual(plans[0].items, [{ text: "Read the ledger", state: "done" }, { text: "Fix the tax line", state: "now" }]);
});

test("over ACP the box is a prompt, Stop ends the turn, and the Terminal is offered only once a command printed", () => {
  const src = fs.readFileSync(new URL("../src/CodingChat.jsx", import.meta.url), "utf8");
  assert.match(src, /\/api\/tasks\/\$\{tid\}\/agent\/cancel/);
  assert.match(src, /live\.terminal !== false/);
  assert.match(src, /data-tq-plan/);
});

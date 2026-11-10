// A FAILURE IS KEPT WHERE IT HAPPENED (rules part 4, the stress round of 2026-11-10): a coding turn over ACP that the adapter ended with an
// error was said only on the session's Terminal - the chat showed its first words and stopped. Taskuary keeps it as its own update
// (acpcoding._turn, `_meta.taskuary: "error"`), and the chat draws it as the turn's error. A CLI log's failed call (sessionrecord: status
// "failed") and its API error (an `error` step) read as failures too. Invented people.
import assert from "node:assert/strict";
import test from "node:test";
import { chatRows, stepsFromAcp } from "../src/chatStream.js";

const failed = { sessionUpdate: "error", content: { type: "text", text: "The turn failed: API Error: 529 Overloaded - type to carry on." }, _meta: { taskuary: "error" } };
const ACP = [
  { sessionUpdate: "user_message_chunk", content: { type: "text", text: "Why did March double, Erin asks?" } },
  { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "Looking. " } },
  failed,
];

const errorsOf = (rows) => rows.flatMap((r) => r.parts || []).flatMap((p) => p.steps || []).filter((s) => s.status === "error");

test("a turn the adapter failed is an error in that turn, never lost and never the owner's", () => {
  assert.deepEqual(stepsFromAcp(ACP).map((s) => s.k), ["you", "said", "error"]);
  const rows = chatRows({ sessions: [{ sid: "s1", source: "acp", at: "2026-11-10 08:00:00", updates: ACP }] });
  assert.deepEqual(rows.map((r) => r.kind), ["you", "turn"]);
  assert.match(errorsOf(rows)[0].summary, /529 Overloaded - type to carry on/);
});

test("a CLI log's failed call and its API error read as failures", () => {
  const steps = [
    { k: "you", text: "Fix the importer.", at: "2026-11-10 08:00:00" },
    { k: "tool", name: "Bash", text: "pytest -q", args: { command: "pytest -q" }, status: "failed", output: "E   ModuleNotFoundError: ledger", at: "2026-11-10 08:01:00" },
    { k: "error", text: "API Error: 529 Overloaded.", at: "2026-11-10 08:02:00" },
  ];
  const rows = chatRows({ sessions: [{ sid: "s1", source: "Claude Code log", at: "2026-11-10 08:00:00", steps }] });
  const bad = errorsOf(rows);
  assert.equal(bad.length, 2);
  assert.match(bad[1].summary, /529 Overloaded/);
});

test("a call ACP never finished is not drawn done once nothing runs - a permission left open across a restart", () => {
  const ups = [
    { sessionUpdate: "user_message_chunk", content: { type: "text", text: "Comment the totals." } },
    { sessionUpdate: "tool_call", toolCallId: "call_1", title: "Edit totals.py", kind: "edit", status: "pending", rawInput: { file_path: "totals.py" },
      locations: [{ path: "totals.py", line: 1 }], content: [{ type: "diff", path: "totals.py", oldText: "", newText: "# keeps the totals" }] },
  ];
  const ses = { sid: "s1", source: "acp", at: "2026-11-10 08:00:00", updates: ups };
  const steps = (rows) => rows.flatMap((r) => r.parts || []).flatMap((p) => p.steps || (p.type === "edit" ? [p] : []));
  // ...while its turn runs it is at work
  assert.ok(chatRows({ sessions: [{ ...ses, live: true }], live: { working: true } }).at(-1).running);
  const after = chatRows({ sessions: [ses] });
  assert.equal(after.at(-1).running, false);
  assert.ok(!steps(after).some((s) => s.status === "done" || s.type === "edit"), JSON.stringify(steps(after)));
  // ...and one the owner refused (ACP: failed) is no "Edited totals.py" either
  const refused = chatRows({ sessions: [{ ...ses, updates: [...ups, { sessionUpdate: "tool_call_update", toolCallId: "call_1", status: "failed" }] }] });
  assert.deepEqual(steps(refused).map((s) => s.type || s.status), ["error"]);
});

test("an edit that failed and was then made reads recovered, never red, and the made one is the edit row", () => {
  const steps = [
    { k: "you", text: "Fix the rounding.", at: "2026-11-10 08:00:00" },
    { k: "tool", name: "Edit", text: "ledger.py", file: "ledger.py", args: { file_path: "ledger.py" }, status: "failed", output: "String to replace not found", at: "2026-11-10 08:01:00" },
    { k: "tool", name: "Edit", text: "ledger.py", file: "ledger.py", args: { file_path: "ledger.py" }, edit: { parts: [{ old: "a", new: "b" }] }, at: "2026-11-10 08:02:00" },
  ];
  const [, turn] = chatRows({ sessions: [{ sid: "s1", source: "Claude Code log", at: "2026-11-10 08:00:00", steps }] });
  assert.deepEqual(turn.parts.map((p) => p.type), ["work", "edit"]);
  assert.equal(turn.parts[0].steps[0].status, "recovered");
});

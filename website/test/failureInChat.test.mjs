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

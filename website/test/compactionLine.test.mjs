// A COMPACTION IS AN EVENT, NOT THE OWNER'S LINE (the owner, 2026-11-10: "what is this garbage? automated compaction? it shoudl not show it please
// just say it was compacted and while it's going on show compacting like claude code does"). Claude wrote its context summary into its log as a
// user entry, and the coding chat drew it as a huge "You" bubble. Read by structure on both roads - a CLI log's `compact` step (sessionrecord),
// the ACP adapter's compaction call or compaction_update - into one quiet line, and "Compacting…" while one is under way. Invented people.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { COMPACTED, chatRows, compactingNow, originOf, rowMessages, stepsFromAcp } from "../src/chatStream.js";

const LOG = [
  { k: "you", text: "Why did March double, Erin asks?", at: "2026-11-10 08:00:00" },
  { k: "said", text: "Reading the importer.", at: "2026-11-10 08:01:00" },
  { k: "compact", text: "Conversation compacted", at: "2026-11-10 08:20:00" },
  { k: "said", text: "Found it: the cursor reset.", at: "2026-11-10 08:21:00" },
];

test("a compaction in a CLI's log is one event line where it happened, never a bubble", () => {
  const rows = chatRows({ sessions: [{ sid: "s1", source: "Claude Code log", at: "2026-11-10 08:00:00", steps: LOG }] });
  assert.deepEqual(rows.map((r) => r.kind), ["you", "turn", "event", "turn"]);
  assert.equal(rows[2].text, COMPACTED);
  assert.equal(rows.filter((r) => r.kind === "you").length, 1);
  const ms = rowMessages(rows);
  // ...drawn as a press's quiet line ("Conversation compacted · 8:20 AM"), never an input - the turn under it goes on
  assert.equal(originOf({ ...ms[2], metadata: { custom: { press: ms[2].press } } }), "press");
  assert.equal(ms[2].content[0].text, "Conversation compacted");
});

const call = (status, first = false) => ({ sessionUpdate: first ? "tool_call" : "tool_call_update", toolCallId: "cmp-1", status,
  ...(first ? { title: "Compact conversation", kind: "think" } : {}), _meta: { claudeCode: { toolName: "compact" } } });
const ACP = [
  { sessionUpdate: "user_message_chunk", content: { type: "text", text: "Why did March double?" } },
  { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "Reading the importer." } },
  call("in_progress", true),
];

test("over ACP the adapter's compaction is a compact step, and while it runs the working line says Compacting", () => {
  assert.deepEqual(stepsFromAcp(ACP).map((s) => s.k), ["you", "said", "compact"]);
  const running = { sessions: [{ sid: "s1", source: "acp", live: true, at: "2026-11-10 08:00:00", updates: ACP }], live: { working: true } };
  assert.equal(compactingNow(running), true);
  // ...under way it is no line yet, and no tool step either
  assert.deepEqual(chatRows(running).map((r) => r.kind), ["you", "turn"]);
  const done = { ...running, sessions: [{ ...running.sessions[0], updates: [...ACP, call("completed")] }] };
  assert.equal(compactingNow(done), false);
  assert.deepEqual(chatRows(done).map((r) => r.kind), ["you", "turn", "event"]);
  // ...and the ACP compaction updates themselves, to a client that asked for them
  const upd = [{ sessionUpdate: "compaction_update", compactionId: "c9", status: "in_progress" }];
  assert.equal(compactingNow({ sessions: [{ source: "acp", live: true, updates: upd }], live: { working: true } }), true);
  assert.equal(compactingNow({ sessions: [{ source: "acp", live: true, updates: [...upd, { sessionUpdate: "compaction_update", compactionId: "c9", status: "completed" }] }] }), false);
});

test("the working line reads Compacting while one is under way", () => {
  const src = readFileSync(fileURLToPath(new URL("../src/GeneralWorkspace.jsx", import.meta.url)), "utf8");
  assert.match(src, /if \(compacting\) return <CompactingBand since=/);
  assert.match(src, /<span className="tq-aui-band-dot" \/><span>Compacting…<\/span>/);
  assert.match(src, /compacting=\{codingBusy && cc\.compacting\}/);
});

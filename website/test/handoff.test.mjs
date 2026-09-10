// A confirmed hand-off (PW-135/136): when the worker starts, the walk moves on once and nothing is settled -
// the delegated task stays in Unread as Working; a repository still to choose is asked on the card and the
// same confirmation runs again; a failed start or a cancel keeps the item where it is.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterExecute, isHandoff } from "../src/proposalCard.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const coder = { id: "ab12", kind: "task.create_from_message", target: 7, version: 1, params: { kind: "coding" }, label: "Send to the coding agent", settles: true, key: "msg:7", ref: "TQ-0007" };

test("a started hand-off advances; one that needs a repository asks and keeps the item", () => {
  assert.equal(isHandoff(coder), true);
  assert.equal(isHandoff({ ...coder, params: { kind: "task" } }), false);
  const started = afterExecute(coder, { status: "done", outcome: { dispatch: "session", started: true, agent: "coder" } });
  assert.deepEqual([started.settle, started.handoff, started.status], [true, true, "done"]);
  const chat = afterExecute({ ...coder, params: { kind: "general" } }, { status: "done", outcome: { taskId: 7, chat: true } });
  assert.equal(chat.handoff, true);
  const existing = afterExecute(coder, { status: "done", outcome: { dispatch: "session", started: false, existing: true } });
  assert.equal(existing.handoff, false);
  const repo = afterExecute(coder, { status: "error", error: "TQ-0007 needs a repository first - pick one", outcome: { dispatch: "needs_repo", taskId: 7, agent: "coder" } });
  assert.deepEqual([repo.settle, repo.status, repo.repo], [false, "error", { taskId: 7, agent: "coder" }]);
  assert.match(repo.receipt, /Not started/);
  const failed = afterExecute(coder, { status: "error", error: "agent did not start" });
  assert.deepEqual([failed.settle, failed.repo], [false, undefined]);
});

test("the page advances without settling on a started hand-off, and the card asks for the repository", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /if \(p\.kind === "item\.settle" \|\| out\.handoff\) advance\(\); else await done\(null\);/);
  assert.match(view, /repo: out\.repo \|\| null/);
  const card = read("ProposalCard.jsx");
  assert.match(card, /import \{ RepoPicker \} from "\.\/RepoPicker\.jsx"/);
  assert.match(card, /const askRepo = p\.status === "error" && p\.repo\?\.taskId/);
  assert.match(card, /<RepoPicker taskId=\{p\.repo\.taskId\} agent=\{p\.repo\.agent\} onDone=\{\(data\) => \{ if \(data\?\.repo\) onConfirm\?\.\(p\); \}\}/);
});

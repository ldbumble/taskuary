// WHO DOES A TASK, once (taskuary/kinds.json, read through src/kinds.js; the server reads it in taskuary/kinds.py): the task list's
// new-task dialog and the task page's picker typed their own copies with different hints, triage's panel and the agent step a third
// and fourth (the cleanup round, 2026-10-18). These hold the page to the file and fail on a copy coming back.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import json from "../../taskuary/kinds.json" with { type: "json" };
import { AGENT_KINDS, KIND_OPTIONS, KINDS, agentWord, kindLabel, shortKind, verdictLabel } from "../src/kinds.js";
import { kindLabel as panelLabel } from "../src/triageVerdict.js";
import { agentWord as storyWord } from "../src/agentStory.js";

test("kinds.js reads kinds.json: the picker, the panel's destination and the worker's name", () => {
  assert.deepEqual(KINDS, ["task", "general", "coding", "reply"]);
  assert.deepEqual(AGENT_KINDS, ["general", "coding"]);
  assert.equal(KIND_OPTIONS, json.kinds);
  for (const k of json.kinds) { assert.equal(kindLabel(k.key), k.label); assert.equal(verdictLabel(k.key), k.verdict); }
  assert.deepEqual([shortKind("coding"), shortKind(""), kindLabel("setup")], ["coding", "your task", "setup"]);
  assert.deepEqual([agentWord("coding"), agentWord("general"), agentWord("task")], ["the coding agent", "the assistant", "the assistant"]);
  assert.equal(panelLabel, verdictLabel); assert.equal(storyWord, agentWord);
  assert.deepEqual(KIND_OPTIONS.filter((o) => o.made === false).map((o) => o.key), ["reply"], "a reply is never made by hand");
});

const SRC = path.join(process.cwd(), "src");
test("no page file keeps its own table of task kinds or types a kind's label", () => {
  const labels = new Set(json.kinds.flatMap((k) => [k.label, k.verdict, k.hint]).filter((w) => /[\s·]/.test(w)));
  const hits = [];
  for (const f of fs.readdirSync(SRC).filter((f) => /\.(jsx?|mjs)$/.test(f) && f !== "kinds.js")) {
    const code = fs.readFileSync(path.join(SRC, f), "utf8").replace(/(^|\s)\/\/[^\n]*/g, "$1");
    if (/\bKIND_OPTIONS\s*=\s*\[/.test(code)) hits.push(`${f}: KIND_OPTIONS = [`);
    for (const m of code.matchAll(/"((?:[^"\\n]|\.)*)"/g)) if (labels.has(m[1])) hits.push(`${f}: "${m[1]}"`);
  }
  assert.deepEqual(hits, []);
});

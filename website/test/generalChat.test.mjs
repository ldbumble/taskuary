import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(f, import.meta.url)), "utf8");
const workspace = read("../src/GeneralWorkspace.jsx");
const tasks = read("../src/TasksView.jsx");

// A general agent is a chat, the way a coding agent is a terminal. The strip above it used to
// switch the body between the conversation, a fake terminal of the same conversation (which
// staircased every multi-line reply), a browser button and a numbers panel - four things to
// choose between before reading what the agent said (the owner, 2026-09-22).
test("the general workspace has no view switcher - the conversation is the only body", () => {
  const strip = workspace.slice(workspace.indexOf("{!dock && <Box"), workspace.indexOf("{dock && <Box"));
  for (const word of [">Terminal<", ">Numbers<", ">Assistant<", '"Browser"']) assert.doesNotMatch(strip, new RegExp(word));
  assert.match(strip, /Full screen/, "the whole-window toggle stays, like a coding agent's");
  assert.doesNotMatch(workspace, /paneFor|taskuary_general_view|SemanticPanel|TerminalPane/);
});

test("the chat renders with or without a live session - a session only adds the browser split", () => {
  const body = workspace.slice(workspace.indexOf("{session ? ("));
  assert.match(body.slice(0, 400), /<SessionPane[^>]*expectBrowser=\{wantsBrowser\(task\)\}>\{thread\}<\/SessionPane>\s*\) : thread\}/);
});

test("the chat takes the room on the task page, the way a live session does", () => {
  const mount = tasks.slice(tasks.indexOf('workspaceMode === "general"'), tasks.indexOf('workspaceMode === "wrapping"'));
  assert.match(mount, /flex: "1 1 0"/);
  assert.match(mount, /minHeight: \{ xs: 360, md: 420 \}/);
});

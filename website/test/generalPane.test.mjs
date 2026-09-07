import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { paneFor } from "../src/generalPane.js";

const read = (f) => readFileSync(fileURLToPath(new URL(f, import.meta.url)), "utf8");
const workspace = read("../src/GeneralWorkspace.jsx");
const tasks = read("../src/TasksView.jsx");

test("a task with no live session still gets the chat - welcome, composer, and its first question", () => {
  assert.equal(paneFor("assistant", false), "chat");
  assert.equal(paneFor("assistant", true), "chat");
  assert.equal(paneFor(undefined, false), "chat");
});

test("the terminal view says nothing has run rather than going blank", () => {
  assert.equal(paneFor("terminal", true), "terminal");
  assert.equal(paneFor("terminal", false), "terminal-empty");
  assert.equal(paneFor("numbers", false), "numbers");
});

test("the workspace body routes through paneFor and no branch of it renders nothing", () => {
  assert.match(workspace, /const pane = paneFor\(view, !!session\)/);
  const body = workspace.slice(workspace.indexOf('{pane === "numbers"'));
  assert.doesNotMatch(body.slice(0, 800), /:\s*null\}/, "every branch of the workspace body renders something");
});

test("the chat takes the room on the task page, the way a live session does", () => {
  const mount = tasks.slice(tasks.indexOf('workspaceMode === "general"'), tasks.indexOf('workspaceMode === "wrapping"'));
  assert.match(mount, /flex: "1 1 0"/);
  assert.match(mount, /minHeight: \{ xs: 360, md: 420 \}/);
});

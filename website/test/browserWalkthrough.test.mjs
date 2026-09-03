import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("a new walkthrough opens its task and describes the embedded browser", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /verb === "walkthrough"[\s\S]{0,500}onOpenTask\?\.\(d\.taskId\)/);
  assert.match(view, /step-by-step walkthrough\. Its browser opens beside the assistant/);
  const card = read("assistantCards.jsx");
  assert.match(card, />Open walkthrough<\/Button>/);
  assert.doesNotMatch(card.slice(card.indexOf("export function SetupCard")), /Hand it to the coding agent/);
});

test("an embedded terminal never steals focus and scrolls the Assistant upward", () => {
  const cards = read("assistantCards.jsx");
  const terminal = read("TerminalView.jsx");
  assert.match(cards, /TerminalPane[^>]+autoFocus=\{false\}/);
  assert.match(terminal, /!readOnly && autoFocus/);
});

test("an expected walkthrough browser reserves the side-by-side pane while Chrome starts", () => {
  const workspace = read("GeneralWorkspace.jsx");
  const terminal = read("TerminalView.jsx");
  assert.match(workspace, /expectBrowser=\{wantsBrowser\(task\)\}/);
  assert.match(terminal, /browser\.open \|\| expectBrowser/);
  assert.match(terminal, /browser · starting…/);
});

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("a new walkthrough is offered as a link and never yanks the tab", () => {
  const view = read("AssistantView.jsx");
  // it used to navigate away the moment the owner asked for a walk-through, and sixty seconds
  // later the walk-through's own session raised a hand at them from the tab they landed on
  // (the 2026-09-03 break test). The receipt carries the ref; going there is their move.
  const branch = view.slice(view.indexOf('verb === "walkthrough"'), view.indexOf('verb === "walkthrough"') + 500);
  assert.doesNotMatch(branch, /onOpenTask/);
  assert.match(branch, /ref: d\.ref/);
  assert.match(view, /walkthrough\. Open it when you want to start; its browser opens beside the assistant/);
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

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("a new walkthrough is offered as a link and never yanks the tab", () => {
  const view = read("AssistantView.jsx");
  // it used to navigate away the moment the owner asked for a walk-through, and sixty seconds
  // later the walk-through's own session raised a hand at them from the tab they landed on
  // (the 2026-09-03 break test). A set-up is a proposal now (task.setup); confirming it lands a
  // receipt that carries the ref, and going there is their move.
  const branch = view.slice(view.indexOf("const confirmProposal"), view.indexOf("const cancelProposal"));
  assert.doesNotMatch(branch, /onOpenTask/);
  assert.match(branch, /ref: p\.ref/);
  assert.doesNotMatch(view, /onNavigate\("Board"/);
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

test("a browser comes with the task, not from a button on the chat", () => {
  // The chat's strip carried a Browser button for a week (2026-09-14 to 2026-09-22), beside
  // Assistant/Terminal/Numbers view switches; the owner wanted the general agent to be a plain
  // chat window, so the strip lost all four. needs:browser is set where the task is made - the
  // New task dialog, a set-up walk, a workflow with `browser: true` - and the pane reserves its
  // half whenever the task carries the mark. The endpoint that sets it afterwards still exists.
  const workspace = read("GeneralWorkspace.jsx");
  assert.doesNotMatch(workspace, /assistant\/browser|browserOn/);
  assert.match(workspace, /expectBrowser=\{wantsBrowser\(task\)\}/);
});

test("every agent screen can take the whole window - the chat's and the terminal's alike", () => {
  // Agent screens live in two families: the chat workspace (the walk, the task page, the Timeline
  // drawer, an assistant card) and the terminal pane (the task page's coding session, the Wall's
  // tiles, the drawer, a terminal card). A toggle in only the first would have missed the Wall,
  // which is where a pane is smallest (the owner, 2026-09-14: "across both").
  const workspace = read("GeneralWorkspace.jsx");
  const terminal = read("TerminalView.jsx");
  const shared = read("fullScreen.js");
  assert.match(workspace, /import \{ FULL_SX, useFullScreen \} from "\.\/fullScreen\.js"/);
  assert.match(terminal, /import \{ FULL_SX, useFullScreen \} from "\.\/fullScreen\.js"/);
  assert.match(workspace, /\.\.\.\(full && !dock \? FULL_SX : null\)/, "the dock keeps its own expand");
  assert.match(terminal, /\.\.\.\(full \? \{ \.\.\.FULL_SX/);
  assert.match(terminal, /canFull && \(/, "the terminal pane carries its own button");
  assert.match(terminal, /<TerminalPaneInner canFull/, "...and every TerminalPane gets it");
  // one at a time, and Esc always gets you out
  assert.match(shared, /let closeOther = null;/);
  assert.match(shared, /e\.key === "Escape"/);
  assert.doesNotMatch(shared, /localStorage/, "full screen is a moment, not a preference");
});

test("the browser is told the pane's shape, debounced, and never blocks the picture", () => {
  const pane = read("BrowserPane.jsx");
  assert.match(pane, /viewportFor\(r\.width, r\.height\)/);
  assert.match(pane, /if \(!viewportMoved\(shape\.current, want\)\) return;/);
  assert.match(pane, /setTimeout\(\(\) => \{[\s\S]{0,240}?browser\/viewport`, want\)\.catch/);
  assert.match(pane, /new ResizeObserver\(\(\) => \{ paint\(\); fitViewport\(\); \}\)/);
});

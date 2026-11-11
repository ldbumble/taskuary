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
  const terminal = read("TerminalView.jsx");
  assert.match(terminal, /!readOnly && ui\?\.autoFocus/);
  assert.match(terminal, /!readOnly && binding\.autoFocus/);
});

test("a browser takes room only once it is on a page - a task that asks for one reserves nothing (2026-11-04)", () => {
  const workspace = read("GeneralWorkspace.jsx");
  const terminal = read("TerminalView.jsx");
  // the owner: "no browser should open if we don't have a URL" - no pane held for a Chrome still coming up, nor for an empty tab
  assert.doesNotMatch(workspace, /expectBrowser/);
  assert.match(terminal, /showsBrowser\(browser\.open, browser\.url\) \|\| \(stack && seen\)/);
});

test("a browser comes with the task, not from a button on the chat", () => {
  // The chat's strip carried a Browser button for a week (2026-09-14 to 2026-09-22), beside
  // Assistant/Terminal/Numbers view switches; the owner wanted the general agent to be a plain
  // chat window, so the strip lost all four. needs:browser is set where the task is made - the
  // New task dialog, a set-up walk, a workflow with `browser: true` - and the pane shows once the
  // agent opens a page (2026-11-04). The endpoint that sets it afterwards still exists.
  const workspace = read("GeneralWorkspace.jsx");
  assert.doesNotMatch(workspace, /assistant\/browser|browserOn/);
});


test("the browser is told the pane's shape, debounced, and never blocks the picture", () => {
  const pane = read("BrowserPane.jsx");
  assert.match(pane, /viewportFor\(r\.width, r\.height\)/);
  assert.match(pane, /if \(!want \|\| \(!claim && !viewportMoved\(shape\.current, want\)\)\) return;/);
  assert.match(pane, /setTimeout\(\(\) => \{[\s\S]{0,240}?browser\/viewport`, want\)\.catch/);
  assert.match(pane, /new ResizeObserver\(\(\) => \{ paint\(\); fitViewport\(\); \}\)/);
});

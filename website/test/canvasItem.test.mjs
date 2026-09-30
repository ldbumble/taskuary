import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const view = src("AssistantView.jsx"), item = src("CanvasItem.jsx");

// The canvas redesign (docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md): the item on the table is
// the Tasks tab's own task view, and three hard requirements hold it.
test("an item with a task behind it is shown by TaskPage; a proposal, a batch or a meeting keeps its own card", () => {
  // (JSX cannot load under bare node - the rule is read from the source)
  assert.match(item, /export const showsTask = \(card, kind\) => !!card\?\.tid && !\["proposal", "setup", "walk", "brief", "fyis", "meeting"\]\.includes\(kind\)/);
  assert.match(view, /if \(live && canvas && m\.card && showsTask\(c, kind\) && canvas\.folded !== c\.key\) return \(/);
  assert.match(item, /<TaskPage taskId=\{card\.tid\} canvas active/);
});

// HARD REQUIREMENT 1: no terminal redraw corruption. The view's box is the chat body's height in BOTH states - Expand
// hides the conversation around it and never resizes it, so the pty inside can never be grown after it has output.
test("Expand never changes the view's height, so the pane is never grown", () => {
  assert.match(item, /<Box data-tq-canvas-item=\{card\.key\} sx=\{\{ height, display: "flex", minWidth: 0 \}\}>/);
  assert.match(item, /export const canvasItemHeight = \(bodyHeight\) => Math\.max\(420, Math\.round\(\(bodyHeight \|\| 0\) - 26\)\)/);
  assert.match(view, /height: canvasItemHeight\(bodyH\), expanded,/);
  assert.doesNotMatch(view.slice(view.indexOf("const canvasState"), view.indexOf("const canvasState") + 400), /expanded \?/);
  assert.match(src("assistantView.css"), /\.tq-chat-inner\.expanded > :not\(\.tq-canvas-live\) \{ display: none; \}/);
});

// HARD REQUIREMENT 2: no rail rebuild on a click. Fold, unfold and Expand are client state.
test("fold, unfold and expand ask the server for nothing", () => {
  const state = view.slice(view.indexOf("const canvasState"), view.indexOf("const canvasState") + 400);
  assert.doesNotMatch(state, /api\.|loadPile|surface\(/);
  const reopen = view.slice(view.indexOf("reopen: (key, onTable)"), view.indexOf("reopen: (key, onTable)") + 120);
  assert.match(reopen, /if \(onTable\) setFoldedKey\(null\); else pull\(key\);/, "the folded item unfolds in place; an earlier one is a named pull");
});

// HARD REQUIREMENT 3: one live card - only the interactive line mounts a TaskPage (and with it one terminal)
test("only the item on the table is mounted live", () => {
  assert.match(view, /live=\{!old && i === lastCardIdx\}/);
  assert.equal((view.match(/<CanvasItem /g) || []).length, 1);
});

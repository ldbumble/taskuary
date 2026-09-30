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
  assert.match(view, /if \(live && canvas && m\.card && showsTask\(c, kind\) && !foldedNow\) return \(/);
  assert.match(item, /<TaskPage taskId=\{card\.tid\} canvas active/);
});

// HARD REQUIREMENT 1: no terminal redraw corruption. The view's box is the chat body's height in BOTH states - Expand
// hides the conversation around it and never resizes it, so the pty inside can never be grown after it has output.
test("Expand never changes the view's height, so the pane is never grown", () => {
  assert.match(item, /sx=\{\{ height: h, display: "flex", minWidth: 0, scrollMarginTop: "8px",/);
  assert.match(item, /export const canvasItemHeight = \(bodyHeight\) => Math\.max\(420, Math\.round\(\(bodyHeight \|\| 0\) - 26\)\)/);
  assert.match(view, /height: canvasItemHeight\(bodyH\), expanded,/);
  assert.doesNotMatch(view.slice(view.indexOf("const canvasState"), view.indexOf("const canvasState") + 400), /expanded \?/);
  assert.match(src("assistantView.css"), /\.tq-chat-inner\.expanded > :not\(\.tq-canvas-live\) \{ display: none; \}/);
});

// ...and on a phone the view is the screen's height from the start; Expand pins that same box (measured in place) full
// screen with a back arrow - still no resize
test("a phone's full screen pins the same box, never a bigger one", () => {
  assert.match(item, /export const phoneItemHeight = \(innerHeight\) => Math\.max\(420, Math\.round\(\(innerHeight \|\| 0\) - 16\)\)/);
  assert.match(item, /const h = phone \? phoneH : height;/);
  assert.match(item, /if \(r\) setPin\(\{ left: r\.left, width: r\.width \}\);/);
  assert.match(item, /position: "fixed", top: 8, left: pin\.left, width: pin\.width/);
  // ...the arrow the SAME size as the icon it replaces: 2px more re-flowed the strip and the pane grew on the way back
  assert.match(src("TaskPage.jsx"), /backArrow \? <ArrowBackIcon sx=\{\{ fontSize: 15 \}\} \/> : <CloseFullscreenIcon sx=\{\{ fontSize: 15 \}\} \/>\) : <OpenInFullIcon sx=\{\{ fontSize: 15 \}\} \/>/);
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

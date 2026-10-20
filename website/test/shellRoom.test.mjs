import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

// THE SHELL ON THE TABLE HOLDS THE VIEW'S ROOM (G8): a canvas view with no pane is only as tall as what it draws, so a view waiting for
// its task was 22px tall - measured 2026-10-20, a cold #task= link with its read held - which is the dead-end walk's intermittent
// "SEEN sweep remove: only 22px of the card on the table is in view": the item after a Remove still waiting for its read. It stands at
// the canvas's floor until the task arrives; a wait past a second after a press is the walk's SWAP "stood empty" instead.
test("a task view waiting for its task stands at the canvas's floor, not as a 22px strip", () => {
  const page = readFileSync(fileURLToPath(new URL("../src/TaskPage.jsx", import.meta.url)), "utf8");
  assert.match(page, /<Box data-tq-task-loading=\{selected \? "" : undefined\} sx=\{\{ height: "100%", minHeight: canvas && selected \? 340 : undefined,/);
  const item = readFileSync(fileURLToPath(new URL("../src/CanvasItem.jsx", import.meta.url)), "utf8");
  assert.match(item, /CANVAS_ITEM_HEIGHT = "max\(340px, /, "340 is the canvas's own floor - change both together");
});

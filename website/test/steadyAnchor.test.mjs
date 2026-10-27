import assert from "node:assert/strict";
import test from "node:test";

import { steady } from "../src/steadyAnchor.js";

// the overnight walk, 2026-10-26: the lit Remind me folded away under its own picker, which MUI then drew at the screen's corner
test("a popover's anchor keeps the place its button stood once the button is gone", () => {
  let rect = { left: 700, top: 760, width: 90, height: 30, bottom: 790, right: 790 }, connected = true;
  const el = { get isConnected() { return connected; }, getClientRects: () => (connected ? [rect] : []), getBoundingClientRect: () => (connected ? rect : { left: 0, top: 0, width: 0, height: 0, bottom: 0, right: 0 }) };
  const a = steady(el);
  assert.equal(a.nodeType, 1, "MUI reads it as an element");
  rect = { ...rect, left: 650 };
  assert.equal(a.getBoundingClientRect().left, 650, "follows the button while it is drawn");
  connected = false;
  assert.equal(a.getBoundingClientRect().left, 700, "...and keeps where it was pressed once it folds away");
  assert.equal(steady(null), null);
  assert.equal(steady(undefined), undefined);
});

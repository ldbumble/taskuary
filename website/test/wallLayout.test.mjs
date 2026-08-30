import test from "node:test";
import assert from "node:assert/strict";
import { movePane, resizedPaneHeight } from "../src/wallLayout.js";

test("dragging a wall pane moves it to the pane entered", () => {
  assert.deepEqual(movePane(["one", "two", "three"], "one", "three"), ["two", "three", "one"]);
  assert.deepEqual(movePane(["one", "two", "three"], "three", "one"), ["three", "one", "two"]);
});

test("invalid and no-op pane drags preserve the existing order object", () => {
  const order = ["one", "two"];
  assert.equal(movePane(order, "one", "one"), order);
  assert.equal(movePane(order, "missing", "two"), order);
});

test("resize follows the pointer and stops at the minimum pane height", () => {
  assert.equal(resizedPaneHeight(400, 200, 275, 240), 475);
  assert.equal(resizedPaneHeight(400, 200, -100, 240), 240);
});

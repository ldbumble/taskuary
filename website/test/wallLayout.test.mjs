import test from "node:test";
import assert from "node:assert/strict";
import { defaultPaneHeight, holdWrappingSessions, movePane, resizedPaneHeight, wallPaneAtPoint, withoutWallSession } from "../src/wallLayout.js";

test("dragging a wall pane moves it to the pane entered", () => {
  assert.deepEqual(movePane(["one", "two", "three"], "one", "three"), ["two", "three", "one"]);
  assert.deepEqual(movePane(["one", "two", "three"], "three", "one"), ["three", "one", "two"]);
});

test("invalid and no-op pane drags preserve the existing order object", () => {
  const order = ["one", "two"];
  assert.equal(movePane(order, "one", "one"), order);
  assert.equal(movePane(order, "missing", "two"), order);
});

test("pointer dragging finds the wall pane under nested terminal content", () => {
  const pane = { getAttribute: (name) => name === "data-wall-pane" ? "two" : null };
  const nestedTerminalNode = { closest: (selector) => selector === "[data-wall-pane]" ? pane : null };
  const documentLike = { elementFromPoint: (x, y) => x === 40 && y === 80 ? nestedTerminalNode : null };
  assert.equal(wallPaneAtPoint(documentLike, 40, 80), "two");
  assert.equal(wallPaneAtPoint(documentLike, 0, 0), "");
  assert.equal(wallPaneAtPoint(null, 40, 80), "");
});

test("resize follows the pointer and stops at the minimum pane height", () => {
  assert.equal(resizedPaneHeight(400, 200, 275, 240), 475);
  assert.equal(resizedPaneHeight(400, 200, -100, 240), 240);
});

test("one row of wall panes fills the available screen", () => {
  assert.equal(defaultPaneHeight(3, 3), "max(300px, calc((100vh - 104px) / 1))");
  assert.equal(defaultPaneHeight(2, 3), "max(300px, calc((100vh - 104px) / 1))");
});

test("additional wall rows share two screenful rows before scrolling", () => {
  assert.equal(defaultPaneHeight(4, 3), "max(300px, calc((100vh - 116px) / 2))");
  assert.equal(defaultPaneHeight(9, 3), "max(300px, calc((100vh - 116px) / 2))");
});

test("a wrapping pane stays visible after its pty exits until close-out answers", () => {
  const one = { sid: "one" }, two = { sid: "two" };
  assert.deepEqual(holdWrappingSessions([two], [one, two], { one: true }), [two, one]);
  assert.deepEqual(holdWrappingSessions([two], [one, two], {}), [two]);
  assert.deepEqual(holdWrappingSessions([one, two], [one, two], { one: true }), [one, two]);
});

test("successful close-out removes only the pane that answered", () => {
  assert.deepEqual(withoutWallSession([{ sid: "one" }, { sid: "two" }], "one"), [{ sid: "two" }]);
});

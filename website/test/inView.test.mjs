// A LIT MOVE IS ONE THE OWNER CAN SEE (the Advisor matrix's phone pass, 2026-10-20): at 390px a refused send's Redraft stood under the
// phone's docked strip and row - in view by its box, covered by the dock. What covers it is read off the screen and scrolled clear.
import test from "node:test";
import assert from "node:assert/strict";
import { coverOf, floorOf, shiftFor } from "../src/inView.js";

const box = (top, height) => ({ top, height, bottom: top + height });

test("a move under a dock is scrolled up past it, one under a pinned head down from it - read off the screen, not the move", () => {
  // the phone's case: a 275px dock whose middle stands ABOVE the Redraft at its foot - still a dock, below
  assert.equal(shiftFor(box(688, 30), box(464, 275), 844), 688 + 30 - 464 + 8);
  assert.equal(shiftFor(box(40, 30), box(0, 56), 844), -(56 - 40 + 8), "a head over the top half sends it down");
});

test("the cover is the box that holds its place while the page scrolls under it, else what was hit", () => {
  const dock = { nodeType: 1, pos: "sticky" }, row = { nodeType: 1, pos: "static", parentElement: dock }, chip = { nodeType: 1, pos: "static", parentElement: row };
  const el = { nodeType: 1 };
  assert.equal(coverOf(chip, el, (e) => ({ position: e.pos })), dock);
  const plain = { nodeType: 1, pos: "static", parentElement: null };
  assert.equal(coverOf(plain, el, (e) => ({ position: e.pos })), plain);
});

test("a held move's floor is the dock's top inside the scroller, else the scroller's foot", () => {
  const body = { getBoundingClientRect: () => box(144, 601) };
  const withDock = { querySelector: () => ({ getBoundingClientRect: () => box(470, 275) }) };
  assert.equal(floorOf(body, withDock), 470);
  assert.equal(floorOf(body, { querySelector: () => null }), 745, "no dock - the desktop's is outside the conversation");
  assert.equal(floorOf(body, { querySelector: () => ({ getBoundingClientRect: () => box(900, 40) }) }), 745, "a dock below the scroller does not cover it");
});

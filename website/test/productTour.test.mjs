import test from "node:test";
import assert from "node:assert/strict";
import {
  TOUR_STEPS, dimRects, hashWantsTour, holeFor, placeCard, rememberTour, shouldOfferTour,
  tourSeen, tourStatus,
} from "../src/productTour.js";

const store = (start = {}) => {
  const data = { ...start };
  return {
    getItem: (k) => (Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
  };
};

test("the walkthrough names the rooms in a short, jargon-free order", () => {
  assert.deepEqual(TOUR_STEPS.map((s) => s.id),
    ["welcome", "assistant", "pipe", "review", "board", "connections", "done"]);
  for (const step of TOUR_STEPS) {
    assert.ok(step.title.length <= 32, `${step.id} title is a headline, not a sentence`);
    assert.ok(step.body.length <= 220, `${step.id} body stays on one breath`);
    assert.doesNotMatch(step.body, /ingest|classifier|verdict|funnel|TRIAGE\.md|SOUL\.md/i,
      `${step.id} does not ask a new owner to learn the internals`);
  }
  assert.equal(TOUR_STEPS[0].target, null);
  assert.equal(TOUR_STEPS.at(-1).target, null);
  assert.equal(TOUR_STEPS.find((s) => s.id === "review").tab, "Review");
  assert.equal(TOUR_STEPS.find((s) => s.id === "board").tab, "Board");
});

test("a first visit is offered once the setup panel is out of the way", () => {
  assert.equal(shouldOfferTour({ seen: true, demo: true, setupOpen: false }), false);
  assert.equal(shouldOfferTour({ seen: false, demo: true, setupOpen: true }), false);
  assert.equal(shouldOfferTour({ seen: false, demo: true, setupOpen: false }), true);
  assert.equal(shouldOfferTour({ seen: false, demo: false, setupKnown: false, setupOpen: false }), false);
  assert.equal(shouldOfferTour({ seen: false, demo: false, setupOpen: false, setupReady: true, setupKnown: true }), true);
  assert.equal(shouldOfferTour({ seen: false, demo: false, setupOpen: false, setupDismissed: true, setupKnown: true }), true);
  assert.equal(shouldOfferTour({ seen: false, demo: false, setupOpen: false, setupReady: false, setupDismissed: false, setupKnown: true }), false);
});

test("done and skipped both count as seen, and a blank store does not", () => {
  const a = store();
  assert.equal(tourSeen(a), false);
  rememberTour("skipped", a);
  assert.equal(tourStatus(a), "skipped");
  assert.equal(tourSeen(a), true);
  const b = store();
  rememberTour("done", b);
  assert.equal(tourSeen(b), true);
});

test("a #tour hash is the shareable way in", () => {
  assert.equal(hashWantsTour("#tour"), true);
  assert.equal(hashWantsTour("tour"), true);
  assert.equal(hashWantsTour("#task=12"), false);
  assert.equal(hashWantsTour(""), false);
});

test("the spotlight hole is padded, and the dim is four rectangles around it", () => {
  const hole = holeFor({ top: 40, left: 20, width: 100, height: 30, bottom: 70, right: 120 }, 8, 12);
  assert.deepEqual(hole, { top: 32, left: 12, width: 116, height: 46, radius: 12 });
  assert.equal(holeFor(null), null);
  const dims = dimRects(hole, 400, 200);
  assert.equal(dims.length, 4);
  const area = dims.reduce((n, r) => n + r.width * r.height, 0);
  assert.equal(area, 400 * 200 - hole.width * hole.height);
  assert.deepEqual(dimRects(null, 400, 200), [{ top: 0, left: 0, width: 400, height: 200 }]);
});

test("the card sits below a target when there is room, and centres when there is none", () => {
  const below = placeCard({
    target: { top: 40, left: 80, width: 120, height: 24, bottom: 64, right: 200 },
    cardW: 360, cardH: 180, vw: 1200, vh: 800,
  });
  assert.ok(below.top >= 80, "below the target");
  const above = placeCard({
    target: { top: 700, left: 80, width: 120, height: 24, bottom: 724, right: 200 },
    cardW: 360, cardH: 180, vw: 1200, vh: 800,
  });
  assert.ok(above.top + 180 <= 700, "above when the bottom has no room");
  const none = placeCard({ target: null, cardW: 360, cardH: 180, vw: 1200, vh: 800 });
  assert.ok(Math.abs(none.left - (1200 - 360) / 2) < 1);
  const beside = placeCard({
    target: { top: 40, left: 16, width: 500, height: 900, bottom: 940, right: 516 },
    cardW: 360, cardH: 180, vw: 1200, vh: 800,
  });
  assert.ok(beside.left >= 516, "a tall rail puts the card beside it");
  assert.ok(beside.top > 40, "and vertically in the middle of the window, not glued to the top");
});

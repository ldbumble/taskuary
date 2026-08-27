import test from "node:test";
import assert from "node:assert/strict";
import { pollWhileVisible } from "../src/visible.js";

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

test("with no document the interval just runs (node tests, no window)", async () => {
  let n = 0;
  const stop = pollWhileVisible(() => { n += 1; }, 20);
  await wait(55);
  stop();
  assert.ok(n >= 2, `expected a few ticks, got ${n}`);
});

test("a hidden document stops the interval and showing it again restarts it", async () => {
  const listeners = {};
  globalThis.document = {
    visibilityState: "visible",
    addEventListener: (e, fn) => { listeners[e] = fn; },
    removeEventListener: (e) => { delete listeners[e]; },
  };
  let n = 0;
  const stop = pollWhileVisible(() => { n += 1; }, 20);
  await wait(55);
  assert.ok(n >= 2);
  const atHide = n;
  document.visibilityState = "hidden";
  listeners.visibilitychange();
  await wait(55);
  assert.equal(n, atHide, "must not tick while hidden");
  document.visibilityState = "visible";
  listeners.visibilitychange();
  assert.ok(n > atHide, "must tick as soon as the tab is shown, not wait for the interval");
  const atShow = n;
  await wait(55);
  assert.ok(n > atShow, "must keep ticking on the interval once visible");
  stop();
  assert.equal(listeners.visibilitychange, undefined);
  delete globalThis.document;
});

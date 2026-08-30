import test from "node:test";
import assert from "node:assert/strict";
import { pollWhileActive, pollWhileVisible } from "../src/visible.js";

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

test("an active mounted view refreshes immediately instead of waiting for its interval", () => {
  let n = 0;
  const stop = pollWhileActive(true, () => { n += 1; }, 1000);
  assert.equal(n, 1);
  stop();
});

test("an inactive mounted view neither refreshes nor arms a poll", () => {
  let n = 0;
  const stop = pollWhileActive(false, () => { n += 1; }, 1000);
  assert.equal(n, 0);
  assert.equal(stop, undefined);
});

test("an active app tab still waits when the whole browser is hidden", () => {
  const listeners = {};
  globalThis.document = {
    visibilityState: "hidden",
    addEventListener: (e, fn) => { listeners[e] = fn; },
    removeEventListener: (e) => { delete listeners[e]; },
  };
  let n = 0;
  const stop = pollWhileActive(true, () => { n += 1; }, 1000);
  assert.equal(n, 0);
  document.visibilityState = "visible";
  listeners.visibilitychange();
  assert.equal(n, 1, "showing the browser must perform the deferred refresh immediately");
  stop();
  delete globalThis.document;
});

test("with no document the interval just runs (node tests, no window)", async () => {
  let n = 0;
  // a generous window: with a 20ms interval and 55ms of waiting this test starved to one tick
  // whenever a build or pytest ran beside it - the assertion is "it keeps ticking", not "on time"
  const stop = pollWhileVisible(() => { n += 1; }, 20);
  await wait(250);
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

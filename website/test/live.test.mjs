import test from "node:test";
import assert from "node:assert/strict";
import { onLive, __testFanout } from "../src/live.js";

test("a hidden tab defers the event and plays it when shown", () => {
  const listeners = {};
  globalThis.document = {
    visibilityState: "hidden",
    addEventListener: (e, fn) => { listeners[e] = fn; },
    removeEventListener: (e) => { delete listeners[e]; },
  };
  const seen = [];
  const stop = onLive("feed-changed", (ev) => seen.push(ev.type));
  __testFanout({ type: "feed-changed" });
  assert.deepEqual(seen, [], "must not refetch while hidden");
  document.visibilityState = "visible";
  listeners.visibilitychange();
  assert.deepEqual(seen, ["hello"], "showing the tab plays the deferred refresh");
  stop();
  assert.equal(listeners.visibilitychange, undefined);
  delete globalThis.document;
});

test("a visible tab applies the event immediately", () => {
  const listeners = {};
  globalThis.document = {
    visibilityState: "visible",
    addEventListener: (e, fn) => { listeners[e] = fn; },
    removeEventListener: (e) => { delete listeners[e]; },
  };
  const seen = [];
  const stop = onLive("feed-changed", (ev) => seen.push(ev.type));
  __testFanout({ type: "feed-changed" });
  assert.deepEqual(seen, ["feed-changed"]);
  __testFanout({ type: "run-tail" });
  assert.deepEqual(seen, ["feed-changed"], "other kinds do not wake this subscriber");
  stop();
  delete globalThis.document;
});

test("hello wakes every subscriber so a reconnect refetches", () => {
  const listeners = {};
  globalThis.document = {
    visibilityState: "visible",
    addEventListener: (e, fn) => { listeners[e] = fn; },
    removeEventListener: (e) => { delete listeners[e]; },
  };
  const seen = [];
  const a = onLive("feed-changed", (ev) => seen.push("a:" + ev.type));
  const b = onLive("task-changed", (ev) => seen.push("b:" + ev.type));
  __testFanout({ type: "hello" });
  assert.deepEqual(seen, ["a:hello", "b:hello"]);
  a(); b();
  delete globalThis.document;
});

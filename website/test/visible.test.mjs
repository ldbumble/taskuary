import test from "node:test";
import assert from "node:assert/strict";
import { pollCalming, pollWhileActive, pollWhileVisible } from "../src/visible.js";

// Every interval here runs on node:test's fake clock: on real timers a loaded box starved the 20ms
// poll to one tick inside 55ms, and a failed assertion skipped stop(), so the live interval kept the
// process from ever exiting (one `node --test` sat 18 minutes). tick(ms) is "ms passed", exactly.
const fakeClock = (t) => { t.mock.timers.enable({ apis: ["setInterval"] }); return (ms) => t.mock.timers.tick(ms); };

// A fake document whose cleanup runs even when an assertion throws, so no test leaks it or a poll.
function fakeDocument(t, visibilityState) {
  const listeners = {};
  globalThis.document = {
    visibilityState,
    addEventListener: (e, fn) => { listeners[e] = fn; },
    removeEventListener: (e) => { delete listeners[e]; },
  };
  t.after(() => { delete globalThis.document; });
  const show = (state) => { document.visibilityState = state; listeners.visibilitychange(); };
  return { listeners, show };
}

test("an active mounted view refreshes immediately instead of waiting for its interval", (t) => {
  const tick = fakeClock(t);
  let n = 0;
  const stop = pollWhileActive(true, () => { n += 1; }, 1000);
  t.after(stop);
  assert.equal(n, 1);
  tick(999);
  assert.equal(n, 1, "the interval adds nothing before it is due");
  tick(1);
  assert.equal(n, 2);
});

test("an inactive mounted view neither refreshes nor arms a poll", (t) => {
  const tick = fakeClock(t);
  let n = 0;
  const stop = pollWhileActive(false, () => { n += 1; }, 1000);
  assert.equal(n, 0);
  assert.equal(stop, undefined);
  tick(5000);
  assert.equal(n, 0, "no interval was armed");
});

test("an active app tab still waits when the whole browser is hidden", (t) => {
  const tick = fakeClock(t);
  const { show } = fakeDocument(t, "hidden");
  let n = 0;
  const stop = pollWhileActive(true, () => { n += 1; }, 1000);
  t.after(stop);
  assert.equal(n, 0);
  tick(3000);
  assert.equal(n, 0, "a hidden browser must not poll either");
  show("visible");
  assert.equal(n, 1, "showing the browser must perform the deferred refresh immediately");
});

test("with no document the interval just runs (node tests, no window)", (t) => {
  const tick = fakeClock(t);
  let n = 0;
  const stop = pollWhileVisible(() => { n += 1; }, 20);
  t.after(stop);
  assert.equal(n, 0, "pollWhileVisible itself waits for the first interval");
  tick(20); tick(20);
  assert.equal(n, 2, "it keeps ticking, once per interval");
  stop();
  tick(100);
  assert.equal(n, 2, "stop() ends the interval");
});

test("a hidden document stops the interval and showing it again restarts it", (t) => {
  const tick = fakeClock(t);
  const { listeners, show } = fakeDocument(t, "visible");
  let n = 0;
  const stop = pollWhileVisible(() => { n += 1; }, 20);
  t.after(stop);
  tick(20); tick(20);
  assert.equal(n, 2);
  show("hidden");
  tick(200);
  assert.equal(n, 2, "must not tick while hidden");
  show("visible");
  assert.equal(n, 3, "must tick as soon as the tab is shown, not wait for the interval");
  tick(19);
  assert.equal(n, 3, "the interval restarts from the show, not from the old schedule");
  tick(1);
  assert.equal(n, 4, "must keep ticking on the interval once visible");
  stop();
  assert.equal(listeners.visibilitychange, undefined);
  tick(100);
  assert.equal(n, 4, "stop() ends the interval");
});

test("a poll whose reads change nothing calms down, and snaps back on a change", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const flush = () => new Promise((r) => setImmediate(r));
  const at = [], answers = [false, false, false, false, true, false];
  let now = 0, i = 0;
  const step = async (ms) => { for (let k = 0; k < ms; k += 500) { now += 500; t.mock.timers.tick(500); await flush(); } };
  const stop = pollCalming(true, async () => { at.push(now); return answers[i++] ?? false; }, 1000, 4000);
  t.after(stop);
  await flush();
  await step(20000);
  const gaps = at.slice(1).map((x, k) => x - at[k]);
  // read at once; each unchanged read doubles the gap (2s, 4s), held at 4s; the changed fifth read is followed 1s later
  assert.deepEqual(gaps.slice(0, 6), [2000, 4000, 4000, 4000, 1000, 2000]);
});

test("a calming poll reads at once only when asked to, and stops when told", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const flush = () => new Promise((r) => setImmediate(r));
  let n = 0;
  const stop = pollCalming(true, async () => { n += 1; return false; }, 1000, 4000, false);
  await flush();
  assert.equal(n, 0);
  t.mock.timers.tick(1000); await flush();
  assert.equal(n, 1);
  stop();
  t.mock.timers.tick(10000); await flush();
  assert.equal(n, 1);
  assert.equal(pollCalming(false, () => {}, 1000), undefined);
});

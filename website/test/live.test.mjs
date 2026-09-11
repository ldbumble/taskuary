import test from "node:test";
import assert from "node:assert/strict";
import { onLive, holdLive, connect, __testFanout, __testReset } from "../src/live.js";

function FakeWS(url) {
  this.url = url;
  this.readyState = FakeWS.OPEN;
  this.onopen = null; this.onmessage = null; this.onclose = null; this.onerror = null;
  FakeWS.instances.push(this);
}
FakeWS.CONNECTING = 0; FakeWS.OPEN = 1; FakeWS.CLOSING = 2; FakeWS.CLOSED = 3;
FakeWS.instances = [];
FakeWS.prototype.close = function () {
  this.readyState = FakeWS.CLOSED;
  if (this.onclose) this.onclose();
};

async function withSocket(fn) {
  const prev = globalThis.WebSocket;
  FakeWS.instances = [];
  globalThis.WebSocket = FakeWS;
  try { return await fn(); }
  finally {
    __testReset();
    globalThis.WebSocket = prev;
    delete globalThis.localStorage;
    delete globalThis.location;
    delete globalThis.document;
  }
}

function withoutSocket(fn) {
  const prev = globalThis.WebSocket;
  globalThis.WebSocket = undefined;
  try { fn(); }
  finally {
    __testReset();
    globalThis.WebSocket = prev;
    delete globalThis.document;
  }
}

test("a hidden tab defers the event and plays it when shown", () => {
  withoutSocket(() => {
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
  });
});

test("a visible tab applies the event immediately", () => {
  withoutSocket(() => {
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
  });
});

test("hello wakes every subscriber so a reconnect refetches", () => {
  withoutSocket(() => {
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
  });
});

test("a subscriber can listen for more than one kind", () => {
  withoutSocket(() => {
    globalThis.document = {
      visibilityState: "visible",
      addEventListener: () => {},
      removeEventListener: () => {},
    };
    const seen = [];
    const stop = onLive(["feed-changed", "task-changed"], (ev) => seen.push(ev.type));
    __testFanout({ type: "feed-changed" });
    __testFanout({ type: "task-changed" });
    __testFanout({ type: "run-tail" });
    assert.deepEqual(seen, ["feed-changed", "task-changed"]);
    stop();
  });
});

test("the socket carries the page token on the query string", async () => {
  await withSocket(() => {
    globalThis.localStorage = { getItem: () => "s3cret" };
    globalThis.location = { protocol: "https:", host: "desk.example" };
    connect();
    assert.equal(FakeWS.instances.length, 1);
    assert.equal(FakeWS.instances[0].url, "wss://desk.example/api/events/ws?token=s3cret");
  });
});

test("an already-open socket is not replaced", async () => {
  await withSocket(() => {
    globalThis.location = { protocol: "http:", host: "127.0.0.1" };
    connect();
    const first = FakeWS.instances[0];
    connect();
    holdLive();
    assert.equal(FakeWS.instances.length, 1);
    assert.equal(FakeWS.instances[0], first);
  });
});

test("a dropped socket reconnects", async () => {
  await withSocket(async () => {
    globalThis.location = { protocol: "http:", host: "127.0.0.1" };
    const orig = globalThis.setTimeout;
    globalThis.setTimeout = (fn, ms) => orig(fn, Math.min(ms || 0, 5));
    try {
      connect();
      FakeWS.instances[0].close();
      await new Promise((r) => orig(r, 40));
      assert.equal(FakeWS.instances.length, 2, "close must open a second socket");
    } finally {
      globalThis.setTimeout = orig;
    }
  });
});

test("a non-JSON frame is not one of ours", async () => {
  await withSocket(() => {
    globalThis.document = {
      visibilityState: "visible",
      addEventListener: () => {},
      removeEventListener: () => {},
    };
    const seen = [];
    const stop = onLive("feed-changed", (ev) => seen.push(ev.type));
    FakeWS.instances[0].onmessage({ data: "not-json" });
    FakeWS.instances[0].onmessage({ data: '{"type":"feed-changed"}' });
    assert.deepEqual(seen, ["feed-changed"]);
    stop();
  });
});

// A sync lands rows several times a second. Every listener that refetches per row does the same
// expensive read dozens of times - and a plain trailing debounce is starved outright while the rows
// keep coming, which is how a chatty agent left the pile on its 30-second poll (2026-09-10 audit).
test("a burst is one refresh, and a burst that never stops still gets one", async () => {
  await withSocket(async () => {
    globalThis.document = { visibilityState: "visible", addEventListener: () => {}, removeEventListener: () => {} };
    let calls = 0;
    const stop = onLive("feed-changed", () => { calls += 1; }, { wait: 20, max: 60 });
    for (let i = 0; i < 5; i += 1) __testFanout({ type: "feed-changed" });
    assert.equal(calls, 0, "five rows in one tick are not five reads");
    await new Promise((r) => setTimeout(r, 40));
    assert.equal(calls, 1, "the burst settles into exactly one read");

    // ...and now a stream that never lets the timer expire: the ceiling lets one through anyway
    const started = Date.now();
    while (Date.now() - started < 90) { __testFanout({ type: "feed-changed" }); }
    assert.ok(calls >= 2, `the ceiling has to fire during an unbroken stream (calls=${calls})`);
    stop();
  });
});

test("without a wait, onLive still calls straight through", async () => {
  await withSocket(() => {
    globalThis.document = { visibilityState: "visible", addEventListener: () => {}, removeEventListener: () => {} };
    let calls = 0;
    const stop = onLive("feed-changed", () => { calls += 1; });
    __testFanout({ type: "feed-changed" }); __testFanout({ type: "feed-changed" });
    assert.equal(calls, 2);
    stop();
  });
});

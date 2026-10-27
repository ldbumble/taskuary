import test from "node:test";
import assert from "node:assert/strict";
import { onLive, __testFanout, __testReset } from "../src/live.js";
import { TAB, covers, mine, seqOf, stampOf } from "../src/liveSeq.js";

/* THE LOAD-ONCE PASS (2026-10-27; the owner: "yes of course but careful nothing else changes"). A write's wake-up carries its stamp and
   the tab whose press made it; a read says the stamp it began at. The page reads again only for writes it does not hold yet - and waits
   out only the bursts that are nothing but its own presses, whose answers bring the rows; anything else is read at once. */
const visible = () => { globalThis.document = { visibilityState: "visible", addEventListener: () => {}, removeEventListener: () => {} }; };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const done = () => { __testReset(); delete globalThis.document; };

test("a read covers a burst only when it began after every write of it, and never one with an unstamped write", () => {
  assert.equal(covers(12, { seq: 12 }), true);
  assert.equal(covers(12, { seq: 13 }), false, "a write after the read began");
  assert.equal(covers(12, { seq: null }), false, "a write that could not be stamped is always read again");
  assert.equal(covers(null, { seq: 3 }), false, "a read that says nothing covers nothing");
  assert.equal(covers(12, undefined), false, "a hello, an old caller");
  assert.equal(stampOf({ seq: 4 }), 4);
  assert.equal(stampOf({}), null);
  assert.equal(seqOf({ headers: { "x-taskuary-seq": "41" } }), 41);
  assert.equal(seqOf({ headers: {} }), null);
  assert.equal(mine({ by: TAB }), true);
  assert.equal(mine({ by: "another-tab" }), false);
  assert.equal(mine({}), false, "a poll's write is nobody's press");
});

test("a burst is told its newest stamp, null when any of it was unstamped, and whether it was all this page's own", async () => {
  visible();
  try {
    const metas = [];
    const off = onLive("feed-changed", (ev, meta) => metas.push(meta), { wait: 20 });
    __testFanout({ type: "feed-changed", seq: 4, by: TAB }); __testFanout({ type: "feed-changed", seq: 6, by: TAB });
    await wait(40);
    __testFanout({ type: "feed-changed", seq: 7, by: TAB }); __testFanout({ type: "feed-changed" });
    await wait(40);
    off();
    assert.deepEqual(metas.map(({ seq, mine: m }) => ({ seq, mine: m })), [{ seq: 6, mine: true }, { seq: null, mine: false }]);
  } finally { done(); }
});

test("only the page's own presses wait: anything else goes at once, and sends a waiting burst of the page's own with it", async () => {
  visible();
  try {
    const got = [];
    const off = onLive("feed-changed", (ev, meta) => got.push(meta), { wait: (ev) => (mine(ev) ? 60 : 0) });
    __testFanout({ type: "feed-changed", seq: 1 });
    assert.equal(got.length, 1, "an arrival is read at once");
    __testFanout({ type: "feed-changed", seq: 2, by: TAB });
    assert.equal(got.length, 1, "the page's own press waits for its answer");
    __testFanout({ type: "feed-changed", seq: 3 });
    assert.equal(got.length, 2, "an arrival during it goes at once, the press's burst with it");
    assert.deepEqual([got[1].seq, got[1].mine], [3, false]);
    await wait(90);
    assert.equal(got.length, 2, "and nothing is left to fire after");
    off();
  } finally { done(); }
});

test("a burst with anything but the page's own in it keeps its soonest moment - the page's next press does not push it out", async () => {
  visible();
  try {
    const got = [];
    const off = onLive("feed-changed", (ev, meta) => got.push(meta), { wait: (ev) => (mine(ev) ? 200 : 30) });
    __testFanout({ type: "feed-changed", seq: 1 });                 // a sync throttled to 30 ms
    __testFanout({ type: "feed-changed", seq: 2, by: TAB });        // the owner presses meanwhile
    await wait(80);
    assert.equal(got.length, 1, "fired at the arrival's moment, not the press's");
    __testFanout({ type: "feed-changed", seq: 3, by: TAB });
    await wait(60);
    __testFanout({ type: "feed-changed", seq: 4, by: TAB });
    await wait(150);
    assert.equal(got.length, 1, "a burst of the page's own still trails");
    await wait(100);
    assert.equal(got.length, 2);
    off();
  } finally { done(); }
});

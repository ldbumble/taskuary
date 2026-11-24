// ONE BACK OVER ONE LIST (the spec's part E, 2026-11-19): the corner arrow went back through the browser's history, the walk bar's Back to the
// rail's row above, and the walk's Next replaced the address - so the arrow skipped every task Next had moved through, and the two Backs
// landed in different places. Every move he makes or the walk makes is one step of the one list, which a page's Back steps back over; a walk
// row's Back is the row above it (the owner, 2026-11-23) - one function, appLinks.navTarget, says which, for every Back.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canGoBack, navBack, navTarget, onBackTo, recordPlace } from "../src/appLinks.js";
import { walkPlace } from "../src/funnelPile.js";
import { tableOf } from "../src/tableState.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

// the browser's history, as far as the app touches it: a stack of entries, Back pops to the one before and says so (popstate)
const browser = () => {
  const list = [{ state: null, hash: "" }]; let at = 0;
  const w = {
    location: { pathname: "/", search: "", get hash() { return list[at].hash; } },
    history: {
      get state() { return list[at].state; },
      pushState(state, _t, url) { list.splice(at + 1); list.push({ state, hash: url.slice(url.indexOf("#")) || "" }); at += 1; },
      replaceState(state, _t, url) { list[at] = { state, hash: url.slice(url.indexOf("#")) || "" }; },
      back() { if (at > 0) at -= 1; },
    },
    dispatchEvent() {},
  };
  return w;
};

test("Next, Next and a row press are three steps; Back three times walks them in reverse, by either button", () => {
  for (const press of ["corner", "bar"]) {
    globalThis.window = browser();
    // the walk's own moves push as a row press does (AssistantView: every move is a step)
    recordPlace("#task=1", "push");                   // a row pressed: task 1
    recordPlace("#task=2", "push");                   // Next
    recordPlace("#task=3", "push");                   // Next
    recordPlace("#task=7", "push");                   // a row pressed further down
    const seen = [];
    for (let i = 0; i < 3; i += 1) { navBack(); seen.push(window.location.hash); }
    assert.deepEqual(seen, ["#task=3", "#task=2", "#task=1"], press);
    assert.equal(canGoBack(), true);
    navBack(); assert.equal(window.location.hash, "", press);
    assert.equal(canGoBack(), false); navBack(); assert.equal(window.location.hash, "", "never out of the app");
    delete globalThis.window;
  }
});

// ...and ONE BACK ON A SCREEN (the design walk, 2026-11-20): the head's arrow and its "Back to TQ-..." chip went; the bar's Back is the one
test("there is one Back on a screen, and the walk's Next pushes its place", () => {
  const view = read("AssistantView.jsx");
  assert.doesNotMatch(view, /aria-label="Back"|data-tq-back-work|ArrowBackIcon/, "no second Back in the head");
  assert.doesNotMatch(view, /window\.history\.back\(\)/);
  assert.doesNotMatch(view, /if \(!key\) navHow\.current = "replace";/);
});

// TWO KINDS OF PLACE, TWO BACKS (the owner, 2026-11-23: "why is there Back on the first item?? it should be grayed out", and "it can be confusing
// because back can take you from settings to task"): on a walk row Back is the row directly above, greyed on the first; on a page it says where
// it returns, and returns there. One function (appLinks.navTarget) answers both, from what the view IS (funnelPile.walkPlace)
const rail = (on, above) => ({ items: [{ key: "task:1", tid: 1 }, { key: "task:2", tid: 2 }, { key: "task:3", tid: 3 }], walk: { on, above, below: null } });
const onRow = (key, pile, over = null) => walkPlace({ table: tableOf({ current: key, browsing: over }), item: pile.items.find((i) => i.key === key) || { key }, pile });

test("the first row's Back is greyed though he came from elsewhere; the second row's goes to the first", () => {
  globalThis.window = browser();
  recordPlace("#settings=config", "push"); recordPlace("#task=1", "push");            // he came to the first row from a page
  const first = navTarget(onRow("task:1", rail("task:1", null)));
  assert.equal(first.disabled, true); assert.equal(first.to, null); assert.equal(first.why, "nothing above this one");
  recordPlace("#task=2", "push");
  const second = navTarget(onRow("task:2", rail("task:2", "task:1")));
  assert.deepEqual([second.to, second.key, second.disabled, second.label], ["above", "task:1", false, ""]);
  delete globalThis.window;
});

test("an item opened from Search is a page: its Back says where it goes and returns to the place he was on", () => {
  globalThis.window = browser();
  recordPlace("#task=1", "push");                                                       // on the first row
  recordPlace("#task=9", "push");                                                       // Search opens a closed task, no row of the rail
  const back = navTarget(onRow("task:9", rail("task:9", null)));
  assert.deepEqual([back.to, back.label, back.disabled], ["place", "Back to TQ-0001", false]);
  navBack(); assert.equal(window.location.hash, "#task=1");
  delete globalThis.window;
});

test("Settings over the second row goes back to it, and Back there steps up the list, never back to Settings", () => {
  globalThis.window = browser();
  const opened = []; const off = onBackTo((h) => opened.push(h));
  recordPlace("#task=1", "push"); recordPlace("#task=2", "push");
  recordPlace("#settings=config", "push");                                              // Settings opened from the second row
  const page = navTarget(onRow("task:2", rail("task:2", "task:1"), "settings"));
  assert.deepEqual([page.to, page.label], ["place", "Back to TQ-0002"]);
  navBack(); assert.equal(window.location.hash, "#task=2"); assert.deepEqual(opened, ["#task=2"]);
  const row = navTarget(onRow("task:2", rail("task:2", "task:1")));                    // ...landed on the row by the page's Back
  assert.deepEqual([row.to, row.key, row.label], ["above", "task:1", ""], "the row above, not the page he came from");
  off(); delete globalThis.window;
});

test("a page with nothing of ours behind it greys its Back; the walk's end goes to the last row it walked", () => {
  globalThis.window = browser();
  assert.deepEqual([navTarget({ row: false }).disabled, navTarget({ row: false }).why], [true, "nothing to go back to"]);
  const end = walkPlace({ table: tableOf({}), item: null, pile: { items: [], walk: { on: null, above: "task:3", ended: true } } });
  assert.deepEqual([navTarget(end).to, navTarget(end).key], ["above", "task:3"]);
  delete globalThis.window;
});

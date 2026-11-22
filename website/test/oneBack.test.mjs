// ONE BACK OVER ONE LIST (the spec's part E, 2026-11-19): the corner arrow went back through the browser's history, the walk bar's Back to the
// rail's row above, and the walk's Next replaced the address - so the arrow skipped every task Next had moved through, and the two Backs
// landed in different places. Every move he makes or the walk makes is one step of the one list; both Backs (and Alt+Left) step back over it.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canGoBack, navBack, recordPlace } from "../src/appLinks.js";

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
test("the bar's Back is the one navBack, and the walk's Next pushes its place", () => {
  const view = read("AssistantView.jsx");
  assert.doesNotMatch(view, /aria-label="Back"|data-tq-back-work|ArrowBackIcon/, "no second Back in the head");
  assert.match(view, /useVerbs\("nav", \[\{ id: BACK, group: "back", label: btn\("back"\), title: btnHint\("back"\), disabled: !canBack \|\| moving,[^\n]*\n\s*run: navBack \}\]/);
  assert.doesNotMatch(view, /window\.history\.back\(\)/);
  assert.doesNotMatch(view, /const goBack = /);
  assert.doesNotMatch(view, /if \(!key\) navHow\.current = "replace";/);
});

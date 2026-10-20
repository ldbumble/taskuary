import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { canvasRequestFromHash } from "../src/canvasLinks.js";

// Every link the app writes still lands once the tabs are gone (the canvas redesign, 2026-09-29).
test("each old link becomes a canvas request", () => {
  assert.deepEqual(canvasRequestFromHash("#task=123", 4), { kind: "task", tid: 123, n: 4 });
  assert.deepEqual(canvasRequestFromHash("#new-task"), { kind: "new", n: 0 });
  assert.deepEqual(canvasRequestFromHash("#report=17").state, { section: "reports", open: 17 });
  // a failed workflow run's Fix with AI, pressed on its task: the workflow opens with the fix asked for
  assert.deepEqual(canvasRequestFromHash("#report=17&fix=9021").state, { section: "reports", open: 17, fix: 9021 });
  assert.deepEqual(canvasRequestFromHash("#report=new").state, { section: "reports", open: "new-report" });
  assert.deepEqual(canvasRequestFromHash("#report=workflows").state, { section: "workflows", open: null });
  assert.deepEqual(canvasRequestFromHash("#report=new-agent").state, { section: "workflows", open: "new-agent" });
  assert.equal(canvasRequestFromHash("#connector=gmail").area, "connections");
  assert.equal(canvasRequestFromHash("#cli-agents").area, "connections");
  assert.deepEqual(canvasRequestFromHash("#settings=config&group=How%20mail%20is%20sorted").state, { section: "config", open: "How mail is sorted" });
  assert.deepEqual(canvasRequestFromHash("#settings=policies").state, { section: "policies", open: "policies" });
  assert.deepEqual(canvasRequestFromHash("#settings=docs").state, { section: "docs", open: null }, "Docs opens on its shelf of files");
  assert.deepEqual(canvasRequestFromHash("#settings=playbooks").state, { section: "playbooks", open: null }, "Playbooks is a section of its own");
  assert.deepEqual(canvasRequestFromHash("#settings=profiles").state, { section: "profiles", open: null }, "and so is Profiles");
  assert.deepEqual(canvasRequestFromHash("#playbook=weekly-close").state, { section: "playbooks", open: "docs" });
  assert.deepEqual(canvasRequestFromHash("#profiles").state, { section: "profiles", open: null }, "the Profiles section, every profile a card");
});

// THE ONE CANVAS (the owner, 2026-10-20: "it should not take you there regardless"): a link to a message - an idea's "Based on", a
// card's "<name>'s message", the setup list, a bell - is a canvas request for THAT message's card. It used to be left to the rail,
// which opened a second view of the row (Summary / Message / Triage / Agent, "undefined in chat"); that view is gone, and no link may
// resolve to anything but a canvas request.
test("a message link asks the canvas for that message's card, under either spelling", () => {
  assert.deepEqual(canvasRequestFromHash("#msg=12", 3), { kind: "msg", mid: 12, n: 3 });
  assert.deepEqual(canvasRequestFromHash("#message=12"), { kind: "msg", mid: 12, n: 0 });
});

test("no link the app writes resolves to the old row view", () => {
  const src = (f) => fs.readFileSync(path.join(process.cwd(), "src", f), "utf8");
  // every kind a link can ask for has a handler on the canvas, and none of them is a stage panel
  const kinds = new Set(["#task=5", "#msg=5", "#message=5", "#new-task", "#report=3", "#connector=gmail", "#connections", "#settings",
    "#settings=policies", "#hub", "#playbook=x", "#profiles", "#cli-agents"].map((h) => canvasRequestFromHash(h).kind));
  const view = src("AssistantView.jsx");
  for (const k of kinds) assert.match(view, new RegExp(`request\\.kind === "${k}"`), `the canvas opens a ${k} link`);
  // ...and the view itself, and every door into it, is out of the code
  const feed = src("FeedView.jsx");
  for (const gone of ["ReviewCanvas", "CanonicalDetail", "TalkItThrough", "openHash", "openByMid", "openByItem", "drill(", "CLEAR FROM TIMELINE",
    "No message preview available", " in ${"]) assert.ok(!feed.includes(gone), `FeedView still has ${gone}`);
  for (const f of fs.readdirSync(path.join(process.cwd(), "src")).filter((n) => /\.(jsx?|css)$/.test(n))) {
    const s = src(f);
    for (const word of ["CLEAR FROM TIMELINE", "Clear from timeline", "Talk it through\"", ">Talk it through<", "in chat\"}`", "No message preview available"])
      assert.ok(!s.includes(word), `${f} still draws "${word}"`);
  }
});

test("a link that is not a page is left alone", () => {
  assert.equal(canvasRequestFromHash(""), null);
  assert.equal(canvasRequestFromHash("#msg=abc"), null);
  assert.equal(canvasRequestFromHash("#report=nonsense").state.open, null, "an unknown report bucket opens the list, not a blank editor");
});

// the final review (2026-09-29): "#settings=foo" crashed the whole app, on every reload - a page the app does not have
// opens the Settings sections instead
test("a settings link to a page that does not exist opens the section list", () => {
  assert.deepEqual(canvasRequestFromHash("#settings=foo").state, { section: null, open: null });
  assert.deepEqual(canvasRequestFromHash("#settings=config&group=Renamed%20group").state, { section: "config", open: "Renamed group" },
    "a group is checked by the view, which knows the groups");
});

// The set-up walk runs in the Assistant tab, not on a cold row somewhere else.
//
// The card used to post, print "open it when you want to start", and stop - so the owner asked for
// a walk-through and got a task to walk themselves (2026-09-10: "it's supposed to walk me through
// this?"). The chat now binds to that task's own session, which is the one with the browser. The
// browser harness runs in demo mode where mutating requests are denied, so the wiring is proven
// here on the source and by tests/test_setup_walk.py on the server side.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const view = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
const css = fs.readFileSync(path.join(process.cwd(), "src", "assistantView.css"), "utf8");
const handOff = view.slice(view.indexOf("const handOff = async"), view.indexOf("const handOff = async") + 1400);

test("the set-up post enters the walk instead of handing back a link to press later", () => {
  assert.match(handOff, /api\.post\("\/api\/concierge\/setup"/, "still the same endpoint");
  assert.match(handOff, /enterWalk\(\{ tid: data\.taskId/, "the chat binds to the task it just opened");
  assert.doesNotMatch(handOff, /Open it when you want to start/, "the receipt no longer defers the walk");
  assert.doesNotMatch(handOff, /onOpenTask|openTask\(/, "and it does not navigate off the tab (the 2026-09-03 break test)");
});

test("the walk is the task's own conversation, with its browser, mounted right here", () => {
  assert.match(view, /import GeneralWorkspace from "\.\/GeneralWorkspace\.jsx"/);
  assert.match(view, /<GeneralWorkspace task=\{walk\.task\} compact \/>/,
    "GeneralWorkspace owns the session, the provider and the SessionPane browser");
  assert.match(css, /\.tq-walk \{[^}]*flex: 1;[^}]*min-height: 0;/, "it has a parent that can shrink");
});

test("while a walk runs the dock conversation stands down rather than competing for the keyboard", () => {
  assert.match(view, /\{!walk && \(\s*<div className="tq-chat-body"/, "the chat body steps aside");
  assert.match(view, /\{!old && !handoff && !walk && \(\s*<div className="tq-compose">/, "and so does the composer");
  assert.match(view, /\{alert && !old && !handoff && !walk && \(/, "no by-the-way strip over a walk");
});

test("leaving puts down the WALK, never the task or its session", () => {
  const leave = view.slice(view.indexOf("const leaveWalk = ()"), view.indexOf("const leaveWalk = ()") + 300);
  assert.match(leave, /setWalk\(null\)/);
  assert.doesNotMatch(leave, /api\.(post|delete|patch)/, "leaving asks the server for nothing");
  assert.match(view, /onClick=\{leaveWalk\}>Leave the walk</);
});

test("a reload asks the task whether the walk is still one - a stale key restores nothing", () => {
  assert.match(view, /const isOpenWalk = \(t\) =>[^\n]*SourceRef === "assistant:setup"/);
  assert.match(view, /!\["done", "dropped"\]\.includes\(t\.Status\)/);
  const restore = view.slice(view.indexOf("let tid = null;"), view.indexOf("const handOff = async"));
  assert.match(restore, /isOpenWalk\(data\.task\)/, "the server row decides, not the stored id");
  assert.match(restore, /localStorage\.removeItem\(WALK_KEY\)/, "and a dead one is forgotten");
});

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// the owner, 2026-10-14: "It should on top line not on top of the work rail ... when you click on task it should open on the
// assistant canvas ... also task showed up without the number?"
test("the search bar is on the top line, and the rail no longer draws one", () => {
  assert.match(read("TaskHubPage.jsx"), /<SearchBar onOpen=\{\(\) => \{ if \(tab !== "Assistant"\) \{ go\("Assistant"\); setTimeout\(openSearch, 60\); \} else openSearch\(\); \}\} \/>/);
  assert.doesNotMatch(read("FeedView.jsx"), /<SearchBar /);
  assert.match(read("FeedView.jsx"), /window\.addEventListener\(OPEN_SEARCH, o\)/);
});

test("a hit goes on the canvas through the rail's own pull, whatever the mode", () => {
  const f = read("FeedView.jsx");
  assert.match(f, /onOpenTask=\{\(tid, h\) => \(onPull \? onPull\(\{ TaskId: tid, Title: h\?\.title \}\) : onOpenTask\?\.\(tid\)\)\}/);
  assert.match(f, /onOpenMessage=\{\(mid, h\) => \(onPull \? \(onPull\(\{ MessageId: mid, TaskId: h\?\.tid, Subject: h\?\.title \}\), true\) : openByMid\(mid\)\)\}/);
});

test("a row with no message of its own is keyed by its task, never msg:undefined", () => {
  const src = read("AssistantView.jsx").match(/export const keyForRow = [\s\S]*?;\r?\n/)[0].replace("export const keyForRow = ", "return ");
  const keyForRow = new Function(src)();
  assert.equal(keyForRow({ TaskId: 1065, Title: "Check status" }), "task:1065");
  assert.equal(keyForRow({ MessageId: 7, TaskId: 3 }), "msg:7");
  assert.equal(keyForRow({ MessageId: 9, Channel: "report" }), "report:9");
});

// A search pick shows the task - it is not something the owner said (the owner, 2026-10-15: "why does the gray thing show
// up when clicking on searched task. Just show the task").
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("search hits pull quietly, and a quiet pull draws no user bubble", () => {
  const feed = read("FeedView.jsx"), view = read("AssistantView.jsx");
  assert.match(feed, /onPull\(\{ TaskId: tid, Title: h\?\.title \}, \{ quiet: true \}\)/);
  assert.match(feed, /onPull\(\{ MessageId: mid, TaskId: h\?\.tid, Subject: h\?\.title \}, \{ quiet: true \}\)/);
  assert.match(view, /onPull=\{\(r, o\) => pull\(keyForRow\(r\), o\?\.quiet \? null : /);
  // ...and the bubble is only ever the asUser text: no asUser, no user row
  assert.match(view, /const optimisticId = asUser \? /);
});

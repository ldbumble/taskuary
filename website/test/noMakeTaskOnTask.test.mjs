// NO "MAKE A TASK" ON A TASK (the owner, 2026-10-01): an item that already IS a task is never offered to be made one -
// not as Make task, nor as the coding or regular agent's task. The server's chips are gated in concierge.cannot
// (tests/test_taskstate.py); these are the page's own doors.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("an opened fyi line offers Make task and the agents' tasks only when it has no task yet", () => {
  const cards = read("assistantCards.jsx");
  const fyis = cards.slice(cards.indexOf("export function FyisCard"), cards.indexOf("export function WrapupCard"));
  for (const verb of ["mine", "coder", "regular_agent"])
    assert.match(fyis, new RegExp(`\\{i\\.mid && !i\\.tid && <Button[^\\n]*propose\\("${verb}", i\\)`), `${verb} is not offered on a task`);
  assert.match(fyis, /\{i\.mid && <Button[^\n]*onClick=\{\(\) => reply\(i\)\}/, "Reply still is");
});

test("the Timeline tray makes a task only for a message with none", () => {
  const feed = read("FeedView.jsx");
  const tray = feed.slice(feed.indexOf("WORK ON IT</TrayGroupLabel>"), feed.indexOf("CLEAR FROM TIMELINE"));
  assert.match(tray, /\{sel\.TaskId \? \(/);
  assert.ok(tray.indexOf("/mine`") > tray.indexOf(") : ("), "Add to my tasks is the no-task branch");
});

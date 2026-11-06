// A step the agent's own shell, browser or desktop held is the AGENT's: its Approve or Dismiss is pressed where it stands and opens nothing
// (the desktop run, 2026-11-04: a press announced as "<review>:reject" moved the page under the agent it set going again). A draft's Send
// and the task's own moves open the chat they are in - Came from's, where they stand.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const src = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");

test("a held step's press opens nothing; a draft's Send, Mark done and the agent's moves open the chat", () => {
  assert.match(src, /heldRef\.current = new Set\(allReviews\.filter\(\(r\) => r\.Kind === "action"\)\.map\(\(r\) => String\(r\.ReviewId\)\)\);/);
  const m = src.match(/useEffect\(\(\) => onPressing\(\(id\) => \{([\s\S]*?)\}\), \[\]\);/);
  assert.ok(m, "the press handler");
  // the handler's own rule, run on the ids a press announces
  const rule = new Function("id", "heldRef", "CHAT_VERBS", "openSecRef", m[1]);
  const CHAT_VERBS = new Set(["reply", "done", "continue"]);
  const opened = [], openSecRef = { current: (s) => opened.push(s) }, heldRef = { current: new Set(["7"]) };
  for (const id of ["7:approve", "7:reject", "8:approve", "done", "continue", "nat"]) rule(id, heldRef, CHAT_VERBS, openSecRef);
  assert.deepEqual(opened, ["agent", "agent", "agent"]);      // a draft's Send (8), Mark done and Continue; the held step's and Came from's never
});

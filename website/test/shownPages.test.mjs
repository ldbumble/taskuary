// What a chat shows the owner (shownPages.js): a page runs with no network, a CSV reads as a table, and each item sits under
// the answer that made it (the owner, 2026-10-09: "only if the agent thinks it's a good way to understand things").
import test from "node:test";
import assert from "node:assert/strict";
import { CSP, csvRows, lockDown, placeShown } from "../src/shownPages.js";

test("a page gets the no-network policy first, after its doctype so it keeps standards mode", () => {
  const out = lockDown("<!DOCTYPE html><html><head><script>fetch('http://127.0.0.1:7999/api/tasks')</script>");
  assert.match(out, /^<!DOCTYPE html><meta http-equiv="Content-Security-Policy"/);
  assert.match(lockDown("<div>hi</div>"), /^<meta http-equiv="Content-Security-Policy"[^>]*><div>hi<\/div>$/);
  assert.match(CSP, /connect-src 'none'/);
  assert.match(CSP, /form-action 'none'/);
  assert.doesNotMatch(CSP, /127\.0\.0\.1|localhost|connect-src [^;]*https/);
});

test("a CSV reads as rows, quotes and all", () => {
  assert.deepEqual(csvRows('Category,August\r\nSupplies,"$78,400"\n"Say ""hi""",1\n'),
    [["Category", "August"], ["Supplies", "$78,400"], ['Say "hi"', "1"]]);
});

test("each item sits under the answer that made it; one whose answer is not in the thread yet waits at the foot", () => {
  const msgs = [{ id: "comment-1", role: "user" }, { id: "comment-2", role: "assistant" }];
  const { by, foot } = placeShown([{ id: 7, after: "comment-2" }, { id: 8, after: "comment-9" }, { id: 9, after: null }], msgs);
  assert.deepEqual(by, { "comment-2": [{ id: 7, after: "comment-2" }] });
  assert.deepEqual(foot.map((p) => p.id), [8, 9]);
});

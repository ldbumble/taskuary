// What you are typing survives the agent's own progress. The busy poll used to bump a key on the
// thread, which REMOUNTS it - and the draft lives in the composer inside that runtime, so every
// 2.5s tick while an agent worked emptied the box under the owner's fingers, at exactly the moment
// the placeholder invites them to "add something for it to pick up" (the owner, 2026-09-14).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const gw = fs.readFileSync(path.join(process.cwd(), "src", "GeneralWorkspace.jsx"), "utf8");

test("the thread is keyed on the task alone - a poll can never remount it", () => {
  assert.doesNotMatch(gw, /key=\{`\$\{task\.TaskId\}-\$\{/, "a revision in the key is a remount");
  assert.match(gw, /<AssistantThread key=\{task\.TaskId\}/);
  assert.doesNotMatch(gw, /setThreadKey/);
});



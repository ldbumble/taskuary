// A playbook drafted in the conversation is approved in it (the owner, 2026-10-21) - the server says which (taskuary/server.py
// _assistant_payload: playbookDrafts); the page only draws it.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const src = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");

test("a playbook drafted in the chat is drawn in the chat with its Approve and what Approve does", () => {
  assert.match(src, /drafts\.map\(\(r\) => <ReviewDecision key=\{r\.ReviewId\} review=\{r\}/);
  assert.match(src, /drafts=\{data\?\.playbookDrafts \|\| \[\]\}/);
  assert.match(src, /Approve saves this playbook to Reports → Playbooks/);
});

// A skill drafted in the conversation is approved in it (the owner, 2026-10-21) - the server says which (taskuary/server.py
// _assistant_payload: skillDrafts); the page only draws it.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { askNote } from "../src/reviewProposal.js";

const src = fs.readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");

test("a skill drafted in the chat is drawn in the chat with its Approve and what Approve does", () => {
  assert.match(src, /drafts\.map\(\(r\) => <ReviewDecision key=\{r\.ReviewId\} review=\{r\}/);
  assert.match(src, /drafts=\{data\?\.skillDrafts \|\| \[\]\}/);
  assert.match(src, /\{askNote\(drafts\[0\]\)\}/);
  assert.match(askNote({ Kind: "action", Status: "pending", DraftText: JSON.stringify({ action: "save_skill", name: "Month end", text: "# Month end" }) }),
    /^Approve saves this skill to Reports → Skills, where triage and the next agent find it by its description\. Nothing is sent to anyone\.$/);
});

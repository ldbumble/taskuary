// A playbook built with AI keeps Taskuary's own brief to the agent in its Summary (the setup instructions and the example email's raw
// record); the task page showed it as "The ask" (the owner, 2026-10-21: never show it). The title is the ask; the owner's own words
// are in the conversation (taskuary/ownwork.py BRIEFED).
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");

test("a playbook setup task's ask is its title, never the brief in its Summary", () => {
  assert.match(page, /const taskAsk = cleanText\(t\?\.SourceRef === "assistant:playbook" \? t\?\.Title :/);
  assert.match(page, /const askText = \(t\?\.SourceRef === "assistant:playbook" \? "" :/);
});

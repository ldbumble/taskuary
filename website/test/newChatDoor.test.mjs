// THE CHAT DOOR WENT (the owner, 2026-11-09): New offers no Chat with Taskuary tab; askAssistant still hands words to the chat.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { askAssistant, takeAsk } from "../src/askAssistant.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("New has no Chat with Taskuary tab (the owner, 2026-11-09: it looks crazy) - the Assistant's own box takes what fits no tab", () => {
  assert.doesNotMatch(read("NewSheet.jsx"), /key: "chat"/);
  assert.doesNotMatch(read("NewSheet.jsx"), /label: "Chat with Taskuary"/);
});

test("the words wait for the Assistant and are taken once", () => {
  globalThis.window ??= new EventTarget();
  askAssistant("what's still open with Payworth?");
  assert.equal(takeAsk(), "what's still open with Payworth?");
  assert.equal(takeAsk(), null);
});

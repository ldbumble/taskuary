// THE CHAT DOOR WENT (the owner, 2026-11-09): New offers no Chat with Taskuary tab; askAssistant still hands words to the chat.
import assert from "node:assert/strict";

import test from "node:test";
import { askAssistant, takeAsk } from "../src/askAssistant.js";


test("the words wait for the Assistant and are taken once", () => {
  globalThis.window ??= new EventTarget();
  askAssistant("what's still open with Payworth?");
  assert.equal(takeAsk(), "what's still open with Payworth?");
  assert.equal(takeAsk(), null);
});

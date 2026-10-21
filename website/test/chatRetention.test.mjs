// Past chats are read a page at a time and never mutated by being listed (PW-157); the retention knob is the
// owner's (PW-158); New chat clears without a turn of its own (PW-156).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the chats panel pages with a cursor and offers earlier chats", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /api\.get\("\/api\/concierge\/chats", \{ params: \{ limit: 25 \}, timeout: 10000 \}\)/);
  assert.match(view, /params: \{ limit: 25, before: chatsNext \}/);
  assert.match(view, /setChatsNext\(data\.next \|\| null\)/);
  assert.match(view, />Earlier chats<\/button>/);
  const newChat = view.slice(view.indexOf("const swapChat = async"), view.indexOf("const openOld"));
  assert.match(newChat, /swapChat\("\/api\/assistant\/dock\/new"\)/);
  assert.doesNotMatch(newChat, /surface\(|turn\(\{ mode/);                     // a blank chat waits for the owner
});

// an earlier chat could only be read - going back to where it left off meant making a task of it (TQ-1161)
test("an earlier chat can be continued, through the same swap New chat uses", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /const continueOld = \(\) => old && swapChat\(`\/api\/concierge\/chats\/\$\{old\.taskId\}\/continue`\)/);
  assert.match(view, /onClick=\{continueOld\}[^>]*>Continue this chat<\/button>/);
});

test("the retention knob is on the Assistant page of Settings", () => {
  // the knob table is taskuary/settings_schema.json now, one file for the page and the assistant
  const schema = JSON.parse(readFileSync(fileURLToPath(new URL("../../taskuary/settings_schema.json", import.meta.url)), "utf8"));
  const knob = schema.knobs.chat_keep_days;
  assert.deepEqual([knob.group, knob.label, knob.type], ["Assistant", "Keep past chats (days)", "number"]);
});

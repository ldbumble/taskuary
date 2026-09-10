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
  const newChat = view.slice(view.indexOf("const newChat = async"), view.indexOf("const openOld"));
  assert.match(newChat, /api\.post\("\/api\/assistant\/dock\/new"/);
  assert.doesNotMatch(newChat, /surface\(|turn\(\{ mode/);                     // a blank chat waits for the owner
});

test("the retention knob is on the Assistant page of Settings", () => {
  const settings = read("SettingsView.jsx");
  assert.match(settings, /chat_keep_days: \{ group: "Assistant", label: "Keep past chats \(days\)", type: "number"/);
});

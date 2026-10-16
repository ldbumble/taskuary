// A chat task reads as a chat (the owner, 2026-10-15: "my chat, their chat, like a chat history ... same for teams").
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const src = fs.readFileSync(new URL("../src/ChatThread.jsx", import.meta.url), "utf8");
const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
// the pure helpers, without React or MUI
const pure = src.slice(src.indexOf("export const CHAT_CHANNELS"), src.indexOf("const dayOf"));
const { CHAT_CHANNELS, isChatTask, mine, splitBody } = new Function("cleanText",
  `${pure.replace(/export /g, "")}; return { CHAT_CHANNELS, isChatTask, mine, splitBody };`)((s) => String(s || "").trim());

test("WhatsApp and Teams tasks are chats; an email task is not", () => {
  assert.ok(CHAT_CHANNELS.has("whatsapp") && CHAT_CHANNELS.has("teams"));
  assert.ok(isChatTask([{ Channel: "whatsapp" }, { Channel: "whatsapp", Status: "context" }]));
  assert.ok(isChatTask([{ Channel: "teams" }]));
  assert.ok(!isChatTask([{ Channel: "email" }]));
  assert.ok(!isChatTask([{ Channel: "whatsapp", Status: "context" }]));             // only your own lines: nobody to talk to
});

test("yours are your platform lines and what Taskuary sent for you", () => {
  assert.ok(mine({ Status: "context" }) && mine({ Direction: "out" }) && mine({ ReviewSent: true }));
  assert.ok(!mine({ Status: "routed", FromName: "Gabi" }));
});

test("a voice note says so once, and an attachment-only message has no words", () => {
  assert.deepEqual(splitBody("Sounds good.\n\n(🎤 voice note (17s) from WhatsApp, transcribed by Groq (Whisper))"), { words: "Sounds good.", voice: true });
  assert.deepEqual(splitBody("(no text - see the attachment)"), { words: "", voice: false });
});

// SECTION 1 READS EVERY CHANNEL AS CONVERSATIONS (the redesign, 2026-10-16): consecutive chat lines are one-line rows under the
// chat's name in Came from, like an email thread's - the bubbles stay in Close out, over the reply
test("the task card's Came from groups chats and email alike; the chat thread stays in Close out", () => {
  assert.match(page, /const chatTask = !detail\?\.batch && isChatTask\(taskMessages\);/);
  assert.doesNotMatch(page, /\{chatTask && <ChatThread messages=\{taskMessages\} \/>\}/);
  assert.doesNotMatch(page, /newestFirst\(alsoSaid\)/);
  assert.match(page, /const sources = groupConversations\(storedMessages/);
  assert.match(page, /detail\?\.repeats\?\.line && <Typography/);
  assert.match(src, /flexDirection: "column", alignItems: me \? "flex-end" : "flex-start"/);   // yours right, theirs left
});

test("newest first, as every message list reads - and the thread stands over the draft in Close out", () => {
  assert.match(src, /const list = \[\.\.\.messages\]\.sort\(\(a, b\) => tsMs\(b\.SentAt\) - tsMs\(a\.SentAt\)\);/);
  assert.doesNotMatch(src, /scrollTop = el\.scrollHeight/);
  assert.doesNotMatch(src, /maxWidth: 900/);                                  // as wide as the task section
  assert.match(src, /maxWidth: \{ xs: "88%", md: "min\(70%, 640px\)" \}/);      // a bubble stays readable
  assert.match(page, /\{chatTask && <Box sx=\{\{ mb: 1\.2 \}\}>[\s\S]{0,160}<ChatThread messages=\{taskMessages\} maxHeight=\{240\} \/>/);
});

// (the owner, 2026-10-15: "keep the width but center them in the chat ... test all different examples of this with newest message first
// and then for email in both the task side and close out side")
test("the conversation is a centred column with its own line around it", () => {
  assert.match(src, /data-tq-chat-thread="" sx={{ mt: 0.85, width: "100%", maxWidth: 800, mx: "auto"/);
});

test("an email task reads newest first on both sides: every email on the task, theirs and yours over the draft in Close out", () => {
  assert.match(page, /newestFirst\(\[\.\.\.inbound, \.\.\.sentOutside\.map\(\(m\) => \(\{ \.\.\.m, mine: true \}\)\)\]\)/);
  assert.match(page, /\{mailThread\.length > 0 && <Box data-tq-mail-thread=""/);
  assert.match(page, /\{!chatTask && !mailThread\.length && newestFirst\(sentOutside\)/, "never the sent lines twice");
});

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

test("the task card draws the thread for a chat, and the old stack for everything else", () => {
  assert.match(page, /const chatTask = !detail\?\.batch && isChatTask\(taskMessages\);/);
  assert.match(page, /\{chatTask && <ChatThread messages=\{taskMessages\} \/>\}/);
  assert.match(page, /\{!detail\?\.batch && !chatTask && newestFirst\(alsoSaid\)/);
  assert.match(page, /detail\?\.repeats\?\.line && !chatTask/);
  assert.match(src, /flexDirection: "column", alignItems: me \? "flex-end" : "flex-start"/);   // yours right, theirs left
});

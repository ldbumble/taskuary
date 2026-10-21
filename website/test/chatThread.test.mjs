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
// chat's name in Came from, like an email thread's - and Show all turns a chat into its bubbles there (below)
test("the task card's Came from groups chats and email alike", () => {
  assert.doesNotMatch(page, /\{chatTask && <ChatThread messages=\{taskMessages\} \/>\}/);
  assert.doesNotMatch(page, /newestFirst\(alsoSaid\)/);
  assert.match(page, /const sources = groupConversations\(storedMessages/);
  assert.match(page, /detail\?\.repeats\?\.line && <Typography/);
  assert.match(src, /flexDirection: "column", alignItems: me \? "flex-end" : "flex-start"/);   // yours right, theirs left
});

test("newest first, as every message list reads", () => {
  assert.match(src, /const list = \[\.\.\.messages\]\.sort\(\(a, b\) => tsMs\(b\.SentAt\) - tsMs\(a\.SentAt\)\);/);
  assert.doesNotMatch(src, /scrollTop = el\.scrollHeight/);
  assert.doesNotMatch(src, /maxWidth: 900/);                                  // as wide as the task section
  assert.match(src, /maxWidth: \{ xs: "88%", md: "min\(70%, 640px\)" \}/);      // a bubble stays readable
});

// (the owner, 2026-10-15: "keep the width but center them in the chat ... test all different examples of this with newest message first
// and then for email in both the task side and close out side")
test("the conversation is a centred column with its own line around it", () => {
  assert.match(src, /data-tq-chat-thread="" sx={{ mt: 0.85, width: "100%", maxWidth: 800, mx: "auto"/);
});

// THE FULL CHAT IS IN TASK, CONDENSED IN CLOSE OUT (the owner, 2026-10-16: "in close out you have the full chat, it's too confusing.
// full chat should be in task (condensed and full). in close out chats condensed version?")
const closeOut = page.slice(page.indexOf('<WorkflowHeading number="3" title="Close out"'), page.indexOf("<Fold title={`Context & history"));
const cameFrom = page.slice(page.indexOf('<Part label="Came from"'), page.indexOf("</Part>", page.indexOf('<Part label="Came from"')));
test("Show all on a chat draws the back-and-forth in Came from; an email thread keeps its rows", () => {
  assert.match(cameFrom, /\{showAll && isChat\(g\.channel\) \? <ChatThread messages=\{g\.msgs\} maxHeight=\{THREAD_MAX\} \/>/);
  assert.match(cameFrom, /<ConversationRows rows=\{previewRows\(g, 2, showAll\)\} open=\{openMsg\} onOpen=\{setOpenMsg\}/);
  assert.match(cameFrom, /\{expands\(sources\) && <Link component="button"/, "a short chat still offers its bubbles");
  assert.match(cameFrom, /showAll \? "Show less" : `Show all \$\{sourceCount\}`/, "and a way back");
});

// THE GAP IS THE WAY IN (the owner, 2026-10-20: "··· 4 more - Gail Moreno, You" between the messages, and Show all at the top where they
// never looked): the line itself opens the conversation - a real button, so a keyboard reaches it - doing what Show all does
test("the '··· N more' line in Came from opens the whole conversation, the same action as Show all", () => {
  const rows = page.slice(page.indexOf("function ConversationRows("), page.indexOf("// the repo is a filter like the others"));
  assert.match(rows, /r\.gap \? \(onExpand \? \(\s*<Box key=\{`gap\$\{ri\}`\} component="button" type="button" data-tq-conversation-gap="" onClick=\{onExpand\}/);
  assert.match(rows, /"&:focus-visible": \{ outline: `2px solid \$\{ACCENT\}`, outlineOffset: 1 \} \}\}>\s*· · · \{r\.gap\} more - \{r\.names\}<\/Box>/);
  assert.match(cameFrom, /onExpand=\{\(\) => setShowAll\(true\)\}/);
  assert.match(cameFrom, /onClick=\{\(\) => setShowAll\(\(v\) => !v\)\}/, "Show all at the top is the same switch");
  assert.doesNotMatch(closeOut, /onExpand=/, "Close out's gap stays a count - the whole conversation is in Task");
});

test("Close out draws the conversation it answers condensed - the same rows as Task - and points to Task for the whole", () => {
  assert.doesNotMatch(closeOut, /<ChatThread/, "never the full bubbles twice");
  assert.doesNotMatch(page, /mailThread|data-tq-mail-thread/);
  assert.match(closeOut, /\{closeGroup && <Box data-tq-close-conversation=""/);
  assert.match(closeOut, /<ConversationRows rows=\{latestRows\(closeGroup, 4\)\} open=\{openMsg\} onOpen=\{setOpenMsg\} \/>/);
  assert.match(closeOut, /onClick=\{seeWholeConversation\}[\s\S]{0,80}the whole conversation is in Task/);
  assert.match(page, /const seeWholeConversation = \(\) => \{ setShowAll\(true\); setOpenStage\("task"\); setSeekCameFrom\(true\); \};/);
  assert.match(page, /<Box ref=\{cameFromRef\}/);
  assert.equal(page.match(/<ConversationRows /g).length, 2, "one component, two places");
});

test("an email task's Close out is the answered thread's rows; what was sent in another conversation still shows, once", () => {
  assert.match(page, /sources\.find\(\(g\) => g\.msgs\.some\(\(m\) => m\.MessageId === sourceMessage\?\.MessageId\)\)/);
  assert.match(page, /const sentApart = newestFirst\(sentOutside\.filter\(\(m\) => !closeGroup\?\.msgs\.some/, "never the sent lines twice");
  assert.match(closeOut, /\{sentApart\.map\(\(m\) => \(/);
});

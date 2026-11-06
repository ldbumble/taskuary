// THE CHAT PICKER (chatPicker.js, ChatPicker.jsx): one dropdown for the Assistant chat and the agent channels (the owner, 2026-11-06: "why
// is it not the same code with dropdown above"). Names shown, only-you / group / direct marked, typing filters, Look again, a row a
// binding cannot take greyed with why.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { WA_TIP, chatHint, chatId, chatName, chatTag, chatUrl, filterChats, isBlocked, noChats, pickedChat } from "../src/chatPicker.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const ROWS = [
  { to: "15550001111-1600000000@g.us", name: "Alex Doyle (you)", kind: "you", people: 1, blocked: "your Assistant chat - it already reaches the coding agents" },
  { to: "15550001111-1700000000@g.us", name: "Coding", kind: "you", people: 1, blocked: "" },
  { to: "120363000000000001@g.us", name: "Northwind ledger team", kind: "group", people: 5, blocked: "" },
  { to: "15550102233@s.whatsapp.net", name: "Gail Moreno", kind: "direct", phone: "+1 555-010-2233", blocked: "" },
  { to: "C0LEDGER", name: "#ledger", kind: "group", people: null },
];

test("each row is marked only you, a group with its size, or direct", () => {
  assert.deepEqual(ROWS.map(chatTag), ["only you", "only you", "group · 5 people", "direct", "group"]);
  assert.equal(chatTag({}), "direct");
});

test("a row shows its name, and its id small under it only where the name is not the id", () => {
  assert.equal(chatName(ROWS[2]), "Northwind ledger team");
  assert.equal(chatId(ROWS[2]), "120363000000000001@g.us");
  assert.equal(chatId(ROWS[4]), "C0LEDGER");
  assert.equal(chatId({ to: "C0X", name: "C0X" }), "");
});

test("typing filters the whole list by name - never by a WhatsApp JID - and an empty box shows every row", () => {
  assert.equal(filterChats(ROWS, "").length, ROWS.length, "the closed picker is not cut to five");
  assert.deepEqual(filterChats(ROWS, "ledger").map((o) => o.name), ["Northwind ledger team", "#ledger"]);
  assert.deepEqual(filterChats(ROWS, "gail").map((o) => o.name), ["Gail Moreno"]);
  assert.deepEqual(filterChats(ROWS, "120363"), [], "the JID is never what finds it");
});

test("the chat picked is a row - and one the list lost is still shown by its id", () => {
  assert.equal(pickedChat(ROWS, "C0LEDGER").name, "#ledger");
  assert.equal(pickedChat(ROWS, "C0GONE").to, "C0GONE");
  assert.equal(pickedChat(ROWS, ""), null);
});

test("a chat a binding cannot take stays listed, greyed with why", () => {
  assert.equal(isBlocked(ROWS[0]), true);
  assert.equal(isBlocked(ROWS[1]), false);
  assert.match(read("ChatPicker.jsx"), /getOptionDisabled=\{isBlocked\}/);
  assert.match(read("ChatPicker.jsx"), /\{o\.blocked && <Typography/);
});

test("WhatsApp gets the only-you group tip; the empty list says what to do next", () => {
  assert.equal(chatHint("whatsapp"), WA_TIP);
  assert.equal(WA_TIP, "Tip: make a WhatsApp group with only you in it (e.g. Coding) and pick it here.");
  assert.equal(chatHint("slack"), "");
  assert.match(noChats("whatsapp"), /message yourself/);
  assert.match(noChats("slack", { agent: true }), /invite the Taskuary app/);
  for (const k of ["whatsapp", "telegram", "slack", "teams"]) assert.match(noChats(k, { agent: true }), /Look again/);
});

test("one endpoint for every picker; an agent channel asks it to mark what it cannot bind", () => {
  assert.equal(chatUrl("whatsapp"), "/api/chats/whatsapp");
  assert.equal(chatUrl("slack", { agent: true }), "/api/chats/slack?agent=1");
});

test("the Assistant chat and the agent channel form draw the one ChatPicker - no datalist, no list of their own", () => {
  const ac = read("AgentChannels.jsx"), sv = read("SettingsView.jsx");
  assert.match(ac, /import ChatPicker from "\.\/ChatPicker\.jsx"/);
  assert.match(ac, /<ChatPicker options=\{chats\} value=\{chat\} onChange=\{setChat\} onLook=\{\(\) => loadChats\(kind\)\}/);
  assert.match(ac, /api\.get\(chatUrl\(kd, \{ agent: true \}\)\)/);
  assert.match(ac, /hint=\{chatHint\(kind\)\}/);
  assert.doesNotMatch(ac, /datalist|k\.chats/);
  assert.match(sv, /import ChatPicker from "\.\/ChatPicker\.jsx"/);
  assert.match(sv, /<ChatPicker options=\{r\.options\}/);
  assert.doesNotMatch(sv, /<Autocomplete/, "the Assistant chat's own dropdown is the shared one now");
  // ...and the task's "Talk to this agent from…" popover is the same ChannelSetup
  assert.match(ac, /<AgentChannels|ChannelSetup taskId=\{taskId\}/);
});

import test from "node:test";
import assert from "node:assert/strict";
import { createChatRoster } from "./roster.mjs";

test("the roster exposes only chats, named and ordered by account recency", () => {
  const roster = createChatRoster();
  roster.upsertContact({ id: "1555@s.whatsapp.net", name: "Dana Reed" });
  roster.upsertContact({ id: "not-a-chat", name: "Nope" });
  roster.upsertChat({ id: "1555@s.whatsapp.net", conversationTimestamp: 100 });
  roster.upsertChat({ id: "42@g.us", subject: "Operations", lastMessageRecvTimestamp: 200 });
  assert.deepEqual(roster.list().map(({ jid, name }) => ({ jid, name })), [
    { jid: "42@g.us", name: "Operations" },
    { jid: "1555@s.whatsapp.net", name: "Dana Reed" }
  ]);
});

test("live traffic refreshes recency without using message text", () => {
  const roster = createChatRoster();
  roster.observeMessage({ key: { remoteJid: "1555@s.whatsapp.net", fromMe: false },
    pushName: "Dana", messageTimestamp: 300, message: { conversation: "private" } });
  roster.observeMessage({ key: { remoteJid: "42@g.us", fromMe: false },
    pushName: "a participant, not the group", messageTimestamp: 200 });
  const rows = roster.list();
  assert.equal(rows[0].name, "Dana");
  assert.equal(rows[0].n, 1);
  assert.equal(rows[0].text, undefined);
  assert.equal(rows[1].name, "");
});

test("blocked routing metadata is merged without opening the chat", () => {
  const roster = createChatRoster();
  assert.deepEqual(roster.list([{ jid: "closed@g.us", group: true, last: 250 }])[0], {
    jid: "closed@g.us", group: true, name: "", last: 250, n: 0
  });
});

test("a reconnect replaces groups with the ones the account still belongs to", () => {
  const roster = createChatRoster();
  roster.upsertChat({ id: "old@g.us", subject: "Old" });
  roster.upsertChat({ id: "1555@s.whatsapp.net" });
  roster.replaceGroups([{ id: "current@g.us", subject: "Current" }]);
  assert.deepEqual(roster.list().map((x) => x.jid), ["1555@s.whatsapp.net", "current@g.us"]);
});

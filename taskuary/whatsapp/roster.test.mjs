import test from "node:test";
import assert from "node:assert/strict";
import { createChatRoster } from "./roster.mjs";
import { createChatGate, createLidMap } from "./policy.mjs";

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

test("a group carries how many people are in it, and an older row stays unknown", () => {
  // the number prefix cannot tell the owner's own Message-yourself thread from a group they made,
  // so the count is what does (2026-09-17)
  const roster = createChatRoster();
  roster.upsertChat({ id: "15550100100-1600000001@g.us", subject: "Myself", participants: [{ id: "me" }] });
  roster.upsertChat({ id: "15550100100-1600000002@g.us", subject: "Jogging",
    participants: [{ id: "me" }, { id: "a" }, { id: "b" }] });
  roster.upsertChat({ id: "120363000000000001@g.us", subject: "The Northwind Team" });
  const by = Object.fromEntries(roster.list().map((r) => [r.name, r.people]));
  assert.equal(by.Myself, 1);
  assert.equal(by.Jogging, 3);
  assert.equal("people" in roster.list().find((r) => r.name === "The Northwind Team"), false);
});

test("an address-book contact is a searchable chat before anyone writes, under the name the owner saved", () => {
  // the bridge downloads no history, so a person only ever arrived as a bare number the first
  // time they wrote - search by name found nobody, by phone number found them (2026-10-21)
  const roster = createChatRoster();
  roster.upsertContact({ id: "15550100200@s.whatsapp.net", name: "Ray Colton" });
  roster.upsertContact({ id: "15550100300@s.whatsapp.net", notify: "a group participant's profile name" });
  assert.deepEqual(roster.list(), [
    { jid: "15550100200@s.whatsapp.net", group: false, name: "Ray Colton", last: 0, n: 0 }
  ]);
});

// WhatsApp writes most 1:1 chats to a LID now (2026-10-23): a LID was "not a chat" here, so a person written to by LID could not
// be listed, picked or let in. A LID is a direct chat; one whose number is known is that number's row, under the saved name.
test("a LID is a direct chat, and a LID whose number is known is one row under the number", () => {
  const lids = createLidMap();
  const gate = createChatGate(() => 0, lids);
  const roster = createChatRoster({ canon: gate.canonical, alt: lids.alt });
  roster.upsertContact({ id: "15550100200@s.whatsapp.net", name: "Ray Colton" });
  roster.observeMessage({ key: { remoteJid: "8000@lid", fromMe: false }, pushName: "Ray", messageTimestamp: 500 });
  roster.observeMessage({ key: { remoteJid: "9000@lid", fromMe: false }, pushName: "Gail", messageTimestamp: 400 });
  assert.deepEqual(roster.list().map(({ jid, name, group }) => [jid, name, group]),
    [["8000@lid", "Ray", false], ["9000@lid", "Gail", false], ["15550100200@s.whatsapp.net", "Ray Colton", false]], "unmapped: listed as they are");
  lids.learn("8000@lid", "15550100200@s.whatsapp.net");
  assert.deepEqual(roster.list().map(({ jid, name, last, n }) => [jid, name, last, n]),
    [["15550100200@s.whatsapp.net", "Ray Colton", 500, 1], ["9000@lid", "Gail", 400, 1]], "mapped: one row, the number, the saved name");
});

test("a contact saved under its LID carries its saved name to the number row", () => {
  const lids = createLidMap();
  const roster = createChatRoster({ canon: (j) => lids.pnOf(j) || j, alt: lids.alt });
  roster.upsertContact({ id: "8000@lid", jid: "15550100200@s.whatsapp.net", lid: "8000@lid", name: "Ray Colton" });
  lids.learn("8000@lid", "15550100200@s.whatsapp.net");
  assert.deepEqual(roster.list().map(({ jid, name }) => [jid, name]), [["15550100200@s.whatsapp.net", "Ray Colton"]]);
});

test("the saved name outlives the profile name a message carries", () => {
  const roster = createChatRoster();
  roster.upsertContact({ id: "15550100200@s.whatsapp.net", name: "Ray Colton" });
  roster.observeMessage({ key: { remoteJid: "15550100200@s.whatsapp.net", fromMe: false },
    pushName: "R", messageTimestamp: 300 });
  roster.upsertContact({ id: "15550100200@s.whatsapp.net", notify: "R" });
  roster.upsertChat({ id: "15550100200@s.whatsapp.net", name: "R", conversationTimestamp: 400 });
  assert.equal(roster.list()[0].name, "Ray Colton");
  assert.equal(roster.list()[0].last, 400);
});

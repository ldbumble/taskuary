import test from "node:test";
import assert from "node:assert/strict";
import { createChatGate, createLidMap, nextReconnect, wantsMedia, RECONNECT_DELAYS_MS, STABLE_CONNECTION_MS } from "./policy.mjs";

test("Baileys decrypts only chats Taskuary explicitly authorizes", () => {
  const gate = createChatGate(() => 1_750_000_000_000);
  assert.equal(gate.shouldIgnore("1555@s.whatsapp.net"), true, "closed until Taskuary supplies policy");
  gate.configure({ allDirect: false, jids: ["1555@s.whatsapp.net", "42@g.us"] });
  assert.equal(gate.shouldIgnore("1555@s.whatsapp.net"), false);
  assert.equal(gate.shouldIgnore("42@g.us"), false);
  assert.equal(gate.shouldIgnore("9999@s.whatsapp.net"), true);
  assert.equal(gate.shouldIgnore("99@g.us"), true);
  assert.equal(gate.shouldIgnore("@s.whatsapp.net"), false, "pairing and key traffic remains open");
  assert.deepEqual(gate.blockedChats().map((x) => x.jid), ["9999@s.whatsapp.net", "99@g.us"]);
});

test("the explicit direct-chat wildcard never opens every group", () => {
  const gate = createChatGate();
  gate.configure({ allDirect: true, jids: ["picked@g.us"] });
  assert.equal(gate.shouldIgnore("anyone@s.whatsapp.net"), false);
  assert.equal(gate.shouldIgnore("picked@g.us"), false);
  assert.equal(gate.shouldIgnore("other@g.us"), true);
});

test("reconnects back off, stop after the budget, and reset after a stable connection", () => {
  let attempt = 0;
  for (const delayMs of RECONNECT_DELAYS_MS) {
    const decision = nextReconnect(attempt, 0);
    assert.equal(decision.paused, false);
    assert.equal(decision.delayMs, delayMs);
    attempt = decision.attempt;
  }
  assert.equal(nextReconnect(attempt, 0).paused, true);
  assert.deepEqual(nextReconnect(attempt, STABLE_CONNECTION_MS), {
    paused: false, attempt: 1, delayMs: RECONNECT_DELAYS_MS[0]
  });
});

// A NOTE TO YOURSELF IS STILL A NOTE. Media was skipped for every `fromMe` message, so the owner's
// own voice note arrived with no text and no audio and messengers.py dropped it on the floor - no
// task, and no thumbs-up, because the reaction rides on ingest (the owner, 2026-09-15: "i left
// voice note to create new task on the whatsapp channel myself but it was not picked up").
// What must NOT be fetched is the echo of Taskuary's own outgoing media, which the bridge already
// tracks by message id.
test("your own voice note is fetched; Taskuary's own echo is not", () => {
  const node = { mimetype: "audio/ogg; codecs=opus" };
  assert.equal(wantsMedia(node, { fromMe: true, echo: false }), true, "a note to yourself is a message");
  assert.equal(wantsMedia(node, { fromMe: false, echo: false }), true);
  assert.equal(wantsMedia(node, { fromMe: true, echo: true }), false, "never re-download what we just sent");
  assert.equal(wantsMedia(node, { fromMe: false, echo: true }), false);
});

test("nothing to fetch is not something to fetch", () => {
  assert.equal(wantsMedia(null, { fromMe: false, echo: false }), false);
  assert.equal(wantsMedia(undefined, {}), false);
});

// WhatsApp writes most 1:1 chats to a LID now (2026-10-23). A LID was not a chat to the gate: the message was dropped before
// decryption AND left off the turned-away list, so the picker could not even offer it - and a person picked by phone number was
// never heard once WhatsApp wrote to their LID.
test("a LID chat is turned away like any chat, and a person picked by number is heard at their LID", () => {
  const lids = createLidMap();
  const gate = createChatGate(() => 1_750_000_000_000, lids);
  gate.configure({ jids: ["15550100200@s.whatsapp.net"] });
  assert.equal(gate.shouldIgnore("8000@lid"), true, "unknown LID: closed");
  assert.deepEqual(gate.blockedChats().map((x) => [x.jid, x.group]), [["8000@lid", false]], "and listed, so it can be picked");
  lids.learn("8000@lid", "15550100200@s.whatsapp.net");
  assert.equal(gate.shouldIgnore("8000@lid"), false, "the number's LID is the same person");
  assert.equal(gate.shouldIgnore("8000:3@lid"), false, "on any of their devices");
  assert.equal(gate.canonical("8000@lid"), "15550100200@s.whatsapp.net", "and is passed on under the number they were picked by");
  assert.deepEqual(gate.blockedChats(), [], "no longer turned away");
  assert.equal(gate.shouldIgnore("9000@lid"), true);
  gate.configure({ jids: ["9000@lid"] });
  assert.equal(gate.shouldIgnore("9000@lid"), false, "a LID picked as it is");
  assert.equal(gate.canonical("9000@lid"), "9000@lid");
});

test("a turned-away LID whose number is known is listed once, under the number", () => {
  const lids = createLidMap();
  const gate = createChatGate(() => 1_750_000_000_000, lids);
  gate.configure({ jids: [] });
  gate.shouldIgnore("15550100300@s.whatsapp.net"); gate.shouldIgnore("8100@lid");
  lids.learn("15550100300@s.whatsapp.net", "8100@lid");
  assert.deepEqual(gate.blockedChats().map((x) => x.jid), ["15550100300@s.whatsapp.net"]);
});

test("the owner's own addresses are always heard - their phone's key shares come from there - and are never 'turned away'", () => {
  const gate = createChatGate();
  gate.configure({ jids: ["42@g.us"] });
  assert.equal(gate.shouldIgnore("15550100100@s.whatsapp.net"), true);
  gate.setSelf(["15550100100:12@s.whatsapp.net", "7000:12@lid"]);
  assert.equal(gate.shouldIgnore("15550100100@s.whatsapp.net"), false);
  assert.equal(gate.shouldIgnore("7000:3@lid"), false);
  assert.deepEqual(gate.blockedChats(), []);
  assert.equal(gate.admits("7000@lid"), false, "heard at the gate is not a picked chat: the bridge drops what it says about others");
  assert.equal(gate.admits("42@g.us"), true);
});

test("the map keeps one partner per side and ignores what is not a phone/LID pair", () => {
  const lids = createLidMap(2);
  assert.equal(lids.learn("8000@lid", "15550100200@s.whatsapp.net"), true);
  assert.equal(lids.learn("15550100200:4@s.whatsapp.net", "8000:4@lid"), false, "same pair, any device");
  assert.equal(lids.learn("42@g.us", "8000@lid"), false);
  assert.equal(lids.learn("8000@lid", undefined), false);
  assert.equal(lids.alt("15550100200@s.whatsapp.net"), "8000@lid");
  lids.learn("8000@lid", "15550100999@s.whatsapp.net");
  assert.equal(lids.alt("15550100200@s.whatsapp.net"), "", "a number re-assigned forgets the old pair");
  lids.learn("8001@lid", "15550100201@s.whatsapp.net"); lids.learn("8002@lid", "15550100202@s.whatsapp.net");
  assert.equal(lids.size(), 2, "capped");
});

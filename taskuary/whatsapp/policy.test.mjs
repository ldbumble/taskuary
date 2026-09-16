import test from "node:test";
import assert from "node:assert/strict";
import { createChatGate, nextReconnect, wantsMedia, RECONNECT_DELAYS_MS, STABLE_CONNECTION_MS } from "./policy.mjs";

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

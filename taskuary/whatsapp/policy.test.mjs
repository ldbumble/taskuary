import test from "node:test";
import assert from "node:assert/strict";
import { createChatGate, nextReconnect, RECONNECT_DELAYS_MS, STABLE_CONNECTION_MS } from "./policy.mjs";

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

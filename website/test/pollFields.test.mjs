import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CHAT_CONNECTORS, CHAT_POLL_SECONDS, pollSecondsField, chatClock } from "../src/pollFields.js";

// PW-003/PW-004: one description of the chat connectors' fast clock, shared by every chat card,
// and it has to say what the server actually does (server._quick_due / quick_forever).

test("every chat connector offers the fast-poll interval, mail does not", () => {
  assert.deepEqual(CHAT_CONNECTORS, ["teams", "slack", "telegram", "whatsapp", "imessage", "discord"]);
  for (const type of CHAT_CONNECTORS) {
    const [label, key, placeholder] = pollSecondsField(type);
    assert.equal(key, "poll_seconds", type);
    assert.match(label, /every N seconds/i);
    assert.equal(placeholder, String(CHAT_POLL_SECONDS), `${type} shows the real default`);
  }
  assert.equal(pollSecondsField("outlook"), null);
  assert.equal(pollSecondsField("gmail"), null);
});

test("the effective clock mirrors the server: blank = default, 0 = background sync only, garbage = background sync only", () => {
  assert.deepEqual(chatClock({ type: "teams", cfg: {}, pollMinutes: 10 }), { mode: "fast", seconds: 30 });
  assert.deepEqual(chatClock({ type: "imessage", cfg: { poll_seconds: "60" }, pollMinutes: 10 }), { mode: "fast", seconds: 60 });
  assert.deepEqual(chatClock({ type: "whatsapp", cfg: { poll_seconds: "0" }, pollMinutes: 10 }), { mode: "background", seconds: 600 });
  assert.deepEqual(chatClock({ type: "slack", cfg: { poll_seconds: "lots" }, pollMinutes: 10 }), { mode: "background", seconds: 600 });
  assert.deepEqual(chatClock({ type: "outlook", cfg: {}, pollMinutes: 10 }), { mode: "background", seconds: 600 });
});

test("background sync 0 turns the fast clock off too", () => {
  assert.deepEqual(chatClock({ type: "teams", cfg: { poll_seconds: "30" }, pollMinutes: 0 }), { mode: "off", seconds: 0 });
  assert.deepEqual(chatClock({ type: "teams", cfg: {}, pollMinutes: "0" }), { mode: "off", seconds: 0 });
});

test("the help text states all three semantics and stops singling out one connector", () => {
  for (const type of CHAT_CONNECTORS) {
    const [label, , , helper] = pollSecondsField(type);
    const copy = `${label} ${helper}`;
    assert.match(copy, /blank = 30/i, type);
    assert.match(copy, /0 = /i, type);
    assert.match(copy, /background sync/i, type);
    assert.doesNotMatch(copy, /only (this connector|whatsapp) polls faster/i, type);
    assert.doesNotMatch(copy, /global sync interval/i, `${type}: blank is not the global interval`);
  }
  const [, , , wa] = pollSecondsField("whatsapp");
  assert.match(wa, /every chat|all chats|not only the assistant/i, "WhatsApp's clock covers the connector's intake, not just the assistant chat");
});

test("every chat card and the Settings help are wired to the shared description", () => {
  const view = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
  for (const type of CHAT_CONNECTORS) assert.match(view, new RegExp(`pollSecondsField\\("${type}"\\)`), type);
  assert.doesNotMatch(view, /"poll_seconds"/, "no card keeps a private copy of the field");
  const settings = readFileSync(new URL("../src/SettingsView.jsx", import.meta.url), "utf8");
  assert.match(settings, /poll_minutes:[\s\S]{0,1500}fast clock|poll_minutes:[\s\S]{0,1500}chat connectors/i,
    "Background sync explains that 0 also stops the chat clock");
});

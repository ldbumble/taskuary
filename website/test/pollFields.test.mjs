import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CHAT_CONNECTORS, CHAT_POLL_SECONDS, pollSecondsField } from "../src/pollFields.js";

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

test("the help text states recurring and explicit fetch semantics without singling out one connector", () => {
  for (const type of CHAT_CONNECTORS) {
    const [label, , , helper] = pollSecondsField(type);
    const copy = `${label} ${helper}`;
    assert.match(copy, /blank = 30/i, type);
    assert.match(copy, /0 = no fast polling/i, type);
    assert.match(copy, /recurring background sync can still poll/i, type);
    assert.match(copy, /manual Sync now, action-time freshness checks, and startup catch-up/i, type);
    assert.match(copy, /Background sync 0 in Settings disables both recurring clocks/i, type);
    assert.match(copy, /explicit and startup fetches remain available/i, type);
    assert.doesNotMatch(copy, /only (this connector|whatsapp) polls faster/i, type);
    assert.doesNotMatch(copy, /global sync interval/i, `${type}: blank is not the global interval`);
    assert.doesNotMatch(copy, /never holds a chat back/i, type);
  }
  const [, , , wa] = pollSecondsField("whatsapp");
  assert.match(wa, /inbound messages from every chat/i);
  assert.match(wa, /not only the assistant chat/i);
  assert.match(wa, /replies in the notification chat are polled/i);
  assert.match(wa, /sending notifications is event-driven/i);
});

test("every chat card and the Settings help are wired to the shared description", () => {
  const view = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
  for (const type of CHAT_CONNECTORS) assert.match(view, new RegExp(`pollSecondsField\\("${type}"\\)`), type);
  assert.doesNotMatch(view, /"poll_seconds"/, "no card keeps a private copy of the field");
  const settings = readFileSync(new URL("../src/SettingsView.jsx", import.meta.url), "utf8");
  const pollHelp = settings.slice(settings.indexOf("poll_minutes:"), settings.indexOf("startup_sync_days:"));
  assert.match(pollHelp, /0 turns recurring background polling off/);
  assert.match(pollHelp, /Sync now, startup catch-up, and an action that must refresh chat context can still fetch/);
  assert.match(pollHelp, /0 here disables both recurring clocks/);
  assert.doesNotMatch(pollHelp, /Sync now as the only road|never holds a chat back/);
});

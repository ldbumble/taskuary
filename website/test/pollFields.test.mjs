import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CHAT_CONNECTORS, CHAT_POLL_SECONDS, isPollField, pollSecondsField } from "../src/pollFields.js";

// PW-003/PW-004: one description of the chat connectors' fast clock, shared by every chat card,
// and it has to say what the server actually does (server._quick_due / quick_forever).

test("every chat connector offers the fast-poll interval, mail does not", () => {
  assert.deepEqual(CHAT_CONNECTORS, ["teams", "slack", "telegram", "whatsapp", "imessage", "discord"]);
  for (const type of CHAT_CONNECTORS) {
    const f = pollSecondsField(type), [label, key, placeholder] = f;
    assert.equal(key, "poll_seconds", type);
    assert.ok(isPollField(f), type);
    assert.match(label, /every \(seconds\)/i);
    assert.equal(placeholder, String(CHAT_POLL_SECONDS), `${type} shows the real default`);
  }
  assert.equal(pollSecondsField("outlook"), null);
  assert.equal(pollSecondsField("gmail"), null);
});

// the setup sweep, 2026-10-28: a cut-off label and a five-line hint - one short label, one line of hint
test("the label is short and the hint is one line that still says blank, zero and what still reads it", () => {
  for (const type of CHAT_CONNECTORS) {
    const [label, , , helper] = pollSecondsField(type);
    assert.ok(label.length <= 40, `${type}: ${label}`);
    assert.ok(helper.length <= 100 && !helper.includes("\n"), `${type}: ${helper}`);
    assert.match(helper, /Blank = 30/, type);
    assert.match(helper, /0 = no fast check/, type);
    assert.match(helper, /background sync and Sync now still read it/, type);
  }
});

test("every chat card and the Settings help are wired to the shared description", () => {
  const view = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
  for (const type of CHAT_CONNECTORS) assert.match(view, new RegExp(`pollSecondsField\\("${type}"\\)`), type);
  assert.doesNotMatch(view, /"poll_seconds"/, "no card keeps a private copy of the field");
  assert.match(view, /isPollField/, "the card draws it apart, under Advanced");
  // the knob's words live in taskuary/settings_schema.json now (one file for the page and the assistant)
  const schema = JSON.parse(readFileSync(new URL("../../taskuary/settings_schema.json", import.meta.url), "utf8"));
  const pollHelp = `${schema.knobs.poll_minutes.desc} ${schema.knobs.poll_minutes.help || ""}`;
  assert.match(pollHelp, /0 turns recurring background polling off/);
  assert.match(pollHelp, /Sync now, startup catch-up, and an action that must refresh chat context can still fetch/);
  assert.match(pollHelp, /0 here disables both recurring clocks/);
  assert.doesNotMatch(pollHelp, /Sync now as the only road|never holds a chat back/);
});

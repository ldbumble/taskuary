// Settings → Notifications must never claim a setup works when outbound.py would skip it.
// The rule it mirrors: active AND the notify role AND a chat named AND a channel that sends.
import test from "node:test";
import assert from "node:assert/strict";
import { notifyState, CAN_NOTIFY } from "../src/notify.js";

const conn = (o) => ({ Name: "c", Type: "telegram", Active: 1, Roles: "notify", ConfigJson: "{}", ...o });
const withChat = (o) => conn({ ConfigJson: JSON.stringify({ notify_chat: "-100123" }), ...o });

test("the sendable channels match the backend's list", () => {
  assert.deepEqual([...CAN_NOTIFY].sort(), ["teams", "telegram", "whatsapp"]);
});

test("a fully wired connector reads as pinging, with the chat named", () => {
  const st = notifyState([withChat({ Name: "Telegram" })]);
  assert.equal(st.kind, "pinging");
  assert.match(st.text, /Pinging Telegram · -100123/);
});

test("phone approvals are mentioned only when they are on", () => {
  assert.doesNotMatch(notifyState([withChat({})], "needs_me", false).text, /approve/);
  assert.match(notifyState([withChat({})], "needs_me", true).text, /reply in that chat to approve/);
});

test("the role without a chat is amber, not green", () => {
  const st = notifyState([conn({ Name: "Telegram" })]);
  assert.equal(st.kind, "unnamed");
  assert.match(st.text, /no chat is named yet/);
});

// The bug: a named chat on a switched-OFF connector fell through to "no chat is named yet",
// which is simply false - the chat is named, the connector is off.
test("a named chat on an inactive connector says the connector is off", () => {
  const st = notifyState([withChat({ Name: "Telegram", Active: 0 })]);
  assert.equal(st.kind, "inactive");
  assert.match(st.text, /switched off/);
  assert.doesNotMatch(st.text, /no chat is named/);
});

// The other bug: a channel outbound.py cannot send through was counted as working.
test("a chat named on a channel that cannot send is never green", () => {
  const st = notifyState([withChat({ Name: "Outlook", Type: "outlook" })]);
  assert.notEqual(st.kind, "pinging");
  assert.match(st.text, /Outlook still carries the role but cannot send/);
});

test("a stale role is flagged even alongside a working one", () => {
  const st = notifyState([withChat({ Name: "Telegram" }), withChat({ Name: "Outlook", Type: "outlook" })]);
  assert.equal(st.kind, "pinging");
  assert.match(st.text, /Pinging Telegram/);
  assert.match(st.text, /Outlook still carries the role/);
});

test("level off overrides a working setup", () => {
  const st = notifyState([withChat({})], "off");
  assert.equal(st.kind, "off");
  assert.match(st.text, /Pushes are off/);
});

test("nothing configured at all names the three channels to try", () => {
  const st = notifyState([]);
  assert.equal(st.kind, "none");
  assert.match(st.text, /Telegram, WhatsApp or Teams/);
});

test("connectors without the role are ignored, and bad JSON is not a crash", () => {
  assert.equal(notifyState([conn({ Roles: "report,tool" })]).kind, "none");
  assert.equal(notifyState([conn({ ConfigJson: "{not json" })]).kind, "unnamed");
  assert.equal(notifyState(null).kind, "none");
});

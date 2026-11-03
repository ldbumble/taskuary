import assert from "node:assert/strict";
import test from "node:test";
import {
  emailRecipientOptions, normalizeEmails, recipientLabel, recipientOptions, sendPrefill, validEmail,
} from "../src/recipientOptions.js";

const options = Array.from({ length: 12 }, (_, i) => ({
  to: `chat-${i}`,
  name: i === 10 ? "Northwind Night Shift" : `Conversation ${i}`,
  hint: i === 11 ? "Finance leadership" : `${i + 1} messages`,
}));

test("a fresh recipient picker only shows the five newest options", () => {
  assert.deepEqual(recipientOptions(options, ""), options.slice(0, 5));
});

test("typing searches every option, not only the five visible recents", () => {
  assert.deepEqual(recipientOptions(options, "northwind").map((x) => x.to), ["chat-10"]);
  assert.deepEqual(recipientOptions(options, "FINANCE leadership").map((x) => x.to), ["chat-11"]);
  assert.deepEqual(recipientOptions(options, "chat-9").map((x) => x.to), ["chat-9"]);
});

test("the recognizable name is used as the field label", () => {
  assert.equal(recipientLabel({ to: "opaque-id", name: "Erin Blake" }), "Erin Blake");
  assert.equal(recipientLabel({ to: "opaque-id" }), "opaque-id");
});

test("email recipients can be selected, typed, pasted as a list, and deduplicated", () => {
  assert.deepEqual(normalizeEmails([
    { to: "known@example.com" }, "new@example.com; KNOWN@example.com", "third@example.com, bad",
  ]), ["known@example.com", "new@example.com", "third@example.com"]);
  assert.equal(validEmail("new@example.com"), true);
  assert.equal(validEmail("not an email"), false);
});

test("a typed address is offered alongside searchable known contacts", () => {
  assert.equal(emailRecipientOptions(options, "outside@example.com")[0], "outside@example.com");
  assert.deepEqual(emailRecipientOptions(options, "Northwind").map((x) => x.to), ["chat-10"]);
});

// the owner, 2026-11-02: the Assistant's "write to the team WhatsApp group" opened Send something on email with To empty
test("Send something opens on the channel it was asked for, its chat in To", () => {
  const grp = "120363000000000001@g.us", targets = [{ channel: "email", to: [] }, { channel: "whatsapp", to: [{ to: grp, name: "Northwind team" }] }];
  assert.deepEqual(sendPrefill(targets, "whatsapp", grp), { channel: "whatsapp", to: grp, emailTo: [] });
  assert.deepEqual(sendPrefill(targets, "whatsapp", ""), { channel: "whatsapp", to: "", emailTo: [] });
  assert.deepEqual(sendPrefill(targets, "email", "gail@northwind.example"), { channel: "email", to: "", emailTo: ["gail@northwind.example"] });
  // ...a channel this install cannot send on keeps the card's own default, and its recipient goes in no other box
  assert.deepEqual(sendPrefill(targets, "telegram", "@erin"), { channel: "", to: "", emailTo: [] });
});

import assert from "node:assert/strict";
import test from "node:test";
import {
  emailRecipientOptions, normalizeEmails, recipientLabel, recipientOptions, validEmail,
} from "../src/recipientOptions.js";

const options = Array.from({ length: 12 }, (_, i) => ({
  to: `chat-${i}`,
  name: i === 10 ? "Ashgrove Night Shift" : `Conversation ${i}`,
  hint: i === 11 ? "Finance leadership" : `${i + 1} messages`,
}));

test("a fresh recipient picker only shows the five newest options", () => {
  assert.deepEqual(recipientOptions(options, ""), options.slice(0, 5));
});

test("typing searches every option, not only the five visible recents", () => {
  assert.deepEqual(recipientOptions(options, "ashgrove").map((x) => x.to), ["chat-10"]);
  assert.deepEqual(recipientOptions(options, "FINANCE leadership").map((x) => x.to), ["chat-11"]);
  assert.deepEqual(recipientOptions(options, "chat-9").map((x) => x.to), ["chat-9"]);
});

test("the recognizable name is used as the field label", () => {
  assert.equal(recipientLabel({ to: "opaque-id", name: "Jessica Rockne" }), "Jessica Rockne");
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
  assert.deepEqual(emailRecipientOptions(options, "Ashgrove").map((x) => x.to), ["chat-10"]);
});

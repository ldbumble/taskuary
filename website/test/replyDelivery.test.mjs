import test from "node:test";
import assert from "node:assert/strict";

import { deliveryCc, deliveryFiles, deliveryMeta, deliveryTo, replyContext } from "../src/replyDelivery.js";

const deliver = (obj) => ({ Deliver: JSON.stringify(obj) });

test("a missing, empty or broken Deliver blob reads as no envelope", () => {
  assert.deepEqual(deliveryMeta(null), {});
  assert.deepEqual(deliveryMeta({}), {});
  assert.deepEqual(deliveryMeta({ Deliver: "" }), {});
  assert.deepEqual(deliveryMeta({ Deliver: "null" }), {});
  assert.deepEqual(deliveryMeta({ Deliver: "{not json" }), {});
  assert.deepEqual(deliveryMeta(deliver({ to: "erin@northwind.example" })), { to: "erin@northwind.example" });
});

test("to is taken from Deliver, a list joined with commas and empty entries dropped", () => {
  assert.equal(deliveryTo(deliver({ to: "erin@northwind.example" })), "erin@northwind.example");
  assert.equal(deliveryTo(deliver({ to: "  gail@northwind.example  " })), "gail@northwind.example");
  assert.equal(
    deliveryTo(deliver({ to: ["erin@northwind.example", "", null, "gail@northwind.example"] })),
    "erin@northwind.example, gail@northwind.example",
  );
});

test("without a to, the reply goes back to the sender, then the conversation", () => {
  const sender = { FromName: "Erin Blake", FromEmail: "erin@northwind.example", ConversationId: "conv-1" };
  assert.equal(deliveryTo(sender), "Erin Blake <erin@northwind.example>");
  assert.equal(deliveryTo({ ...sender, FromEmail: "" }), "Erin Blake");
  assert.equal(deliveryTo({ ...sender, FromName: "" }), "erin@northwind.example");
  assert.equal(deliveryTo({ ConversationId: "conv-1" }), "conv-1");
  assert.equal(deliveryTo({}), "this conversation");
  assert.equal(deliveryTo({ ...sender, ...deliver({ to: [] }) }), "Erin Blake <erin@northwind.example>");
});

test("attachments without a name and empty cc entries are dropped", () => {
  const review = deliver({
    attachments: [{ name: "invoice.pdf" }, { size: 10 }, null, { name: "" }, { name: "notes.txt" }],
    cc: ["paula@northwind.example", "", null],
  });
  assert.deepEqual(deliveryFiles(review), [{ name: "invoice.pdf" }, { name: "notes.txt" }]);
  assert.deepEqual(deliveryCc(review), ["paula@northwind.example"]);
  assert.deepEqual(deliveryFiles(deliver({ attachments: "invoice.pdf" })), []);
  assert.deepEqual(deliveryCc(deliver({ cc: "paula@northwind.example" })), []);
  assert.deepEqual(deliveryFiles({}), []);
  assert.deepEqual(deliveryCc({}), []);
});

test("a chat reply names the room it lands in; an email says only who it goes to", () => {
  const erin = { FromName: "Erin Blake", FromEmail: "erin@northwind.example" };
  assert.equal(replyContext({ ...erin, Channel: "email" }), "Erin Blake <erin@northwind.example>");
  assert.equal(replyContext({ ...erin }), "Erin Blake <erin@northwind.example>");
  assert.equal(replyContext({ FromName: "Erin Blake", Channel: "Slack", SourceName: "#ops" }), "Erin Blake in #ops");
  assert.equal(replyContext({ FromName: "Erin Blake", Channel: "teams" }), "Erin Blake in teams");
  assert.equal(replyContext({ FromName: "Erin Blake", Channel: "whatsapp" }), "Erin Blake in the chat");
});

import test from "node:test";
import assert from "node:assert/strict";

import { bareAddresses, deliveryCc,deliveryFiles, deliveryMeta, deliveryTo, needsAddress, replyContext } from "../src/replyDelivery.js";

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

test("a redrafted email keeps the sender's name on the To line: the envelope's bare address is matched to the review's sender", () => {
  const erin = { FromName: "Erin Blake", FromEmail: "Erin@northwind.example" };
  assert.equal(deliveryTo({ ...erin, ...deliver({ kind: "reply", to: ["erin@northwind.example"] }) }), "Erin Blake <erin@northwind.example>");
  assert.equal(deliveryTo({ ...erin, ...deliver({ to: ["erin@northwind.example", "gail@northwind.example"] }) }),
    "Erin Blake <erin@northwind.example>, gail@northwind.example");
  assert.equal(deliveryTo({ ...erin, ...deliver({ to: "Erin B <erin@northwind.example>" }) }), "Erin B <erin@northwind.example>");
  // ...and the To box and its save take the addresses back out
  assert.deepEqual(bareAddresses("Erin Blake <erin@northwind.example>, gail@northwind.example"), ["erin@northwind.example", "gail@northwind.example"]);
  assert.deepEqual(bareAddresses(""), []);
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
  assert.equal(replyContext({ FromName: "Erin Blake", Channel: "teams" }), "Erin Blake in Teams");
  assert.equal(replyContext({ FromName: "Omar Keller", Channel: "telegram" }), "Omar Keller in Telegram");
  assert.equal(replyContext({ FromName: "Erin Blake", Channel: "whatsapp" }), "Erin Blake in the chat");
  // a chat's address is no name, and a one-to-one chat named after the person is no room (the stress run, 2026-11-05)
  assert.equal(replyContext({ FromName: "Ray Colton", FromEmail: "15550000332@s.whatsapp.net", Channel: "whatsapp", SourceName: "Ray Colton" }), "Ray Colton");
  assert.equal(replyContext({ FromName: "Ray Colton", FromEmail: "15550000332@s.whatsapp.net", Channel: "whatsapp", SourceName: "Northwind ops" }), "Ray Colton in Northwind ops");
});

// "To: <a bank's name>" on an agent's email (the owner, 2026-11-09): a To with no address asks for one; a reply to a mail has no To
test("an envelope whose To holds no address needs one - an address, or no To at all, does not", () => {
  assert.equal(needsAddress(deliver({ channel: "email", to: [] })), true);
  assert.equal(needsAddress(deliver({ channel: "email", to: ["Northwind Bank"] })), true);
  assert.equal(needsAddress(deliver({ channel: "email", to: ["treasury@northwind-bank.example"] })), false);
  assert.equal(needsAddress(deliver({ kind: "reply" })), false);
  assert.equal(needsAddress({}), false);
});

test("the card holds Send and opens To while the address is missing", async () => {
  const { readFileSync } = await import("node:fs");
  const rd = readFileSync(new URL("../src/ReviewDecision.jsx", import.meta.url), "utf8");
  assert.match(rd, /needsTo && \[no\("approve"\), no\("send_close"\), no\("anyway"\)\]\.includes\(v\.id\) \? \{ \.\.\.v, disabled: true/);
  assert.match(rd, /needs=\{needsTo\}/);
});

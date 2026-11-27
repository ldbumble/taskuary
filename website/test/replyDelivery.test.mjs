import test from "node:test";
import assert from "node:assert/strict";

import { bareAddresses, deliveryCc,deliveryFiles, deliveryMeta, drawnEnvelope, deliveryTo, needsAddress, replyContext, sentTo } from "../src/replyDelivery.js";

const deliver = (obj) => ({ Deliver: JSON.stringify(obj) });

// red team round 6: the press named only the To it drew - a copy, a subject, a mailbox or a file changed since went under the words he read
test("a press carries the whole envelope its card drew, each file by its content", () => {
  const r = deliver({ channel: "email", to: ["erin@northwind.example"], cc: ["gail@northwind.example"], subject: "Q3 figures", mailbox: "alex@northwind.example",
    seen: 4, attachments: [{ name: "q3.xlsx", path: "C:/x/q3.xlsx", size: 9, sha256: "ab12" }] });
  assert.deepEqual(drawnEnvelope(r), { to: ["erin@northwind.example"], cc: ["gail@northwind.example"], subject: "Q3 figures", mailbox: "alex@northwind.example",
    attachments: [{ name: "q3.xlsx", sha256: "ab12" }] });
  assert.deepEqual(drawnEnvelope({}), { to: null, cc: null, subject: null, mailbox: null, attachments: [] });
  // ...and the From row its read gave it, a reply's too: a task moved to another profile since leaves from another mailbox
  assert.equal(drawnEnvelope({ From: "alex@harbor.example" }).from, "alex@harbor.example");
  assert.equal(drawnEnvelope({ From: null }).from, null);
});

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

// AN EMAIL OF ITS OWN SAYS ITS OWN ENVELOPE (the walks, 2026-11-18): Erin asked by Teams chat, the agent's email went to gail@, and the card and
// its receipt read "To Erin Blake" / "Sent to Erin Blake" - the chat's sender, not the address the send used. The envelope's channel and To decide
test("an email set up on a chat's task names the address it goes to, never the chat's sender", () => {
  const chat = { FromName: "Erin Blake", FromEmail: "erin@teams.example", Channel: "teams", SourceName: "Erin Blake" };
  const email = { ...chat, Deliver: JSON.stringify({ channel: "email", to: ["gail@northwind.example"] }) };
  assert.equal(replyContext(email), "gail@northwind.example");
  assert.equal(sentTo(email), "gail@northwind.example");
  assert.equal(replyContext(chat), "Erin Blake");                                   // ...a reply in the chat itself is still the chat's
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
  assert.match(rd, /needsTo && \[no\("approve"\), no\("anyway"\)\]\.includes\(v\.id\) \? \{ \.\.\.v, disabled: true/);
  assert.match(rd, /needs: needsTo/, "its To field asks for the address");
});
// THE RECEIPT NAMES EVERYONE IT WENT TO (the walk, 2026-11-17): a mail to Erin copying Gail read "To erin@" on its sent card while the agent
// said it went to both. The To box keeps the To alone (its save is the To); what went - the sent card and the line at the press - names the Cc too.
test("what went names the copied, as the agent says it; the To line keeps the To alone", async () => {
  const r = { FromName: "Erin Blake", FromEmail: "erin@northwind.example", ...deliver({ to: ["erin@northwind.example"], cc: ["gail@northwind.example"] }) };
  assert.equal(sentTo(r), "Erin Blake <erin@northwind.example>, copying gail@northwind.example");
  assert.equal(replyContext(r), "Erin Blake <erin@northwind.example>");
  assert.equal(sentTo({ ...deliver({ to: ["erin@northwind.example"], cc: ["gail@northwind.example", "ray@northwind.example"] }) }),
    "erin@northwind.example, copying gail@northwind.example, ray@northwind.example");
  assert.equal(sentTo(deliver({ to: ["erin@northwind.example"] })), "erin@northwind.example");
  const { readFileSync } = await import("node:fs"), src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
  assert.match(src("replyDelivery.js"), /export const sentCardOf = [^\n]*\n[^\n]*to: sentTo\(review\)/);   // ...one reading of a sent card, wherever drawn
  assert.match(src("TaskPage.jsx"), /<SentReview \{\.\.\.sentCardOf\(r\)\}/);
  assert.match(src("ReviewDecision.jsx"), /said: verb === "approve" \? \{[^}]*to: sentTo\(r\)/);
});


test("versions of one letter are a pick on its one card: the box holds one, a pick puts another in, his own words say so", async () => {
  // walk 22 (2026-11-25): "Yes - Thursday" and "No - keep Friday" stood as one card holding only the last
  const { versionPick, versionsOf } = await import("../src/replyDelivery.js");
  const vs = versionsOf({ Versions: JSON.stringify(["Yes - Thursday.", "No - Friday."]) });
  assert.deepEqual(vs, ["Yes - Thursday.", "No - Friday."]); assert.deepEqual(versionsOf({ Versions: null }), []); assert.deepEqual(versionsOf({ Versions: "[\"one\"]" }), []);
  let picked = null; const [f] = versionPick(vs, "Yes - Thursday.", true, (t) => { picked = t; });
  assert.equal(f.type, "choice"); assert.equal(f.value, 0); assert.deepEqual(f.choices.map((c) => c.label), ["Version 1 of 2", "Version 2 of 2"]);
  f.onChange("1"); assert.equal(picked, "No - Friday.");
  assert.deepEqual(versionPick(vs, "Yes, but at 3.", true, () => {})[0].choices.at(-1), { value: "", label: "Your words" });
  assert.deepEqual(versionPick([], "x", true, () => {}), []);
});

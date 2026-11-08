// ONE EMAIL CARD (the owner, 2026-11-08: "share code as much as possible with to/cc/bcc/attach etc"): the reply and the agent's email are one
// card - To, CC, BCC folded until asked for, Subject, files - every field editable and sent with Send; CC and BCC are one row (ui.CcRow)
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { deliveryBcc, deliverySubject } from "../src/replyDelivery.js";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the subject is the envelope's, else Re: the mail answered, and BCC reads like CC", () => {
  assert.equal(deliverySubject({ Deliver: JSON.stringify({ subject: "Q4 review" }), Subject: "Friday" }), "Q4 review");
  assert.equal(deliverySubject({ Subject: "Friday" }), "Re: Friday");
  assert.equal(deliverySubject({ Subject: "RE: Friday" }), "RE: Friday");
  assert.deepEqual(deliveryBcc({ Deliver: JSON.stringify({ bcc: ["ray@northwind.example", ""] }) }), ["ray@northwind.example"]);
});

test("every email card draws the same rows, and the press carries BCC and a changed subject", () => {
  const rd = src("ReviewDecision.jsx"), ui = src("ui.jsx");
  assert.match(ui, /export const CcRow = \(\{ cc, setCc, channel, label: name = "CC" \}\)/);
  assert.match(ui, /export const SubjectRow = /);
  assert.match(rd, /const isEmail = String\(r\.Channel \|\| meta\.channel \|\| ""\)\.toLowerCase\(\) === "email";/);
  assert.match(rd, /<CcRow cc=\{ccNow\} setCc=\{setCc\} channel="email" \/>/);
  assert.match(rd, /<CcRow cc=\{bccNow\} setCc=\{setBcc\} channel="email" label="BCC" \/>/);
  assert.match(rd, /<SubjectRow subject=\{subjNow\} onChange=\{setSubj\}/);
  assert.match(rd, /bcc: bccNow, subject: subj != null && subj !== subjFiled \? subj : null/);
  assert.doesNotMatch(rd, /!isSlot \|\| ccNow\.length > 0/, "an agent's email has the same Add CC as a reply");
});

test("a reply's card reads its subject off the mail it answers, which the task's reviews now carry", () => {
  const store = readFileSync(new URL("../../taskuary/store.py", import.meta.url), "utf8");
  assert.match(store, /m\.ConversationId, m\.Subject FROM review rv /);
});

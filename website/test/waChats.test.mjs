// A WhatsApp chat is found by its name, its phone number in any form, or its group's name - never by its JID; the JID is shown
// small and muted under the name (the owner, 2026-10-23). Every number is a 555-01xx fiction, every group id invented.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { recipientId, recipientLabel, recipientOptions } from "../src/recipientOptions.js";
import { meta } from "../src/searchHits.js";
import { waLabel, waMatches, waPhone } from "../src/waChats.js";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const ERIN = "15550100123@s.whatsapp.net", RAY = "15550100188@s.whatsapp.net", OPS = "120363000000000001@g.us";
const rows = [{ to: ERIN, name: "Erin Blake" }, { to: RAY, name: "" }, { to: OPS, name: "Northwind ops" }];
const find = (q) => rows.filter((r) => waMatches(q, r.to, r.name)).map((r) => r.to);

test("a chat is found by the person's name and the group's name", () => {
  assert.deepEqual(find("erin"), [ERIN]);
  assert.deepEqual(find("BLAKE erin"), [ERIN]);
  assert.deepEqual(find("northwind"), [OPS]);
});

test("a person is found by their number however it is typed", () => {
  for (const q of ["+1 555 010 0123", "+1 (555) 010-0123", "1-555-010-0123", "15550100123", "555.010.0123", "0015550100123", "010-0123"])
    assert.deepEqual(find(q), [ERIN], q);
  assert.deepEqual(find("555 0100"), [ERIN, RAY]);
});

// the owner, 2026-10-26: "the whatsapp contacts people tab are still not searchable by name as well"
test("a person WhatsApp writes to by LID is found by their name, never by the LID, and the picker searches it that way", () => {
  const GAIL = "88001@lid", opts = [{ to: GAIL, name: "Gail Moreno" }, { to: ERIN, name: "Erin Blake" }];
  for (const q of ["gail", "MORENO", "gail moreno"]) assert.deepEqual(opts.filter((o) => waMatches(q, o.to, o.name)).map((o) => o.to), [GAIL], q);
  for (const q of ["88001", GAIL, "lid"]) assert.deepEqual(recipientOptions(opts, q).map((o) => o.to), [], q);
  assert.equal(recipientLabel(opts[0]), "Gail Moreno");
  assert.equal(recipientId(opts[0]), GAIL);
});

test("the JID never finds anything", () => {
  for (const q of ["120363", OPS, "s.whatsapp.net", "@g.us", ERIN]) assert.deepEqual(find(q), [], q);
});

test("the label is the name, else the formatted number, and the JID is the small line under it", () => {
  assert.equal(waLabel(ERIN, "Erin Blake"), "Erin Blake");
  assert.equal(waLabel(RAY, "15550100188"), "+1 555-010-0188");
  assert.equal(waLabel(OPS, ""), "WhatsApp group");
  assert.equal(waPhone(OPS), "");
  assert.equal(recipientLabel({ to: RAY }), "+1 555-010-0188");
  assert.equal(recipientId({ to: RAY }), RAY);
  assert.equal(recipientId({ to: "erin@northwind.example", name: "Erin Blake" }), "", "an email address is not a WhatsApp id");
});

test("the recipient pickers search WhatsApp by name and number, other channels as before", () => {
  const opts = [...rows, { to: "erin@northwind.example", name: "Erin (mail)" }];
  assert.deepEqual(recipientOptions(opts, "erin").map((o) => o.to), [ERIN, "erin@northwind.example"]);
  assert.deepEqual(recipientOptions(opts, "(555) 010-0188").map((o) => o.to), [RAY]);
  assert.deepEqual(recipientOptions(opts, "120363").map((o) => o.to), []);
});

test("a WhatsApp source hit in Ctrl K reads its JID as the small grey line", () => {
  assert.deepEqual(meta({ type: "source", title: "Northwind ops", channel: "whatsapp", sub: OPS }), ["whatsapp", OPS]);
  assert.deepEqual(meta({ type: "source", title: "inbox", channel: "email" }), ["email"]);
});

test("every WhatsApp picker draws the name over a small muted JID and filters through waMatches", () => {
  const card = src("ConnectorsView.jsx");
  assert.match(card, /waMatches\(q, r\.jid, r\.name\)/);
  assert.doesNotMatch(card, /\$\{r\.name \|\| ""\} \$\{r\.jid\}/, "the JID is no longer in what the card searches");
  assert.match(card, /fontWeight: 600 \}\} noWrap>\{waLabel\(r\.jid, r\.name\)\}/);
  assert.match(card, /fontSize: 9\.5, display: "block", opacity: 0\.8 \}\} noWrap>\{r\.jid\}/);
  // ...one chat picker (NewSheet's ChatRecipient), which Email someone draws too
  const s = src("NewSheet.jsx");
  assert.match(s, /\{recipientLabel\(target\)\}<\/Box>/);
  assert.match(s, /\{recipientId\(target\) && <Box sx=\{\{ \.\.\.mono, fontSize: 10, color: FAINT \}\}>/);
  assert.match(s, /filterOptions=\{\(rows, state\) => withFound\(recipientOptions\(rows, state\.inputValue\), found, state\.inputValue\)\}/);
  assert.match(src("EmailSomeone.jsx"), /<ChatRecipient key=\{channel\} channel=\{channel\}/);
  assert.match(src("SettingsView.jsx"), /filterOptions=\{\(o, st\) => recipientOptions\(o, st\.inputValue, o\.length\)\}/);
  assert.match(src("ReportsView.jsx"), /const chatFilter = \(opts, st\) => recipientOptions\(opts, st\.inputValue, 8\)/);
});

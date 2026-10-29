// THE COMBINE SLIDER (the owner, 2026-10-29): each message connection's card carries a 1-5 slider, "Keep separate" .. "Combine",
// whose level triage is handed with every message from that connection type. A mailbox card and the email channel share one level.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { MARKS, SAYS, clampLevel, combines, defaultLevel, kindOf } from "../src/combineLevel.js";

const src = fs.readFileSync(path.join(import.meta.dirname, "..", "src", "ConnectorsView.jsx"), "utf8");

test("defaults: WhatsApp and email 4, everything else 3, a mailbox card is email", () => {
  assert.deepEqual(["whatsapp", "outlook", "gmail", "imap", "teams", "slack", "telegram"].map(defaultLevel), [4, 4, 4, 4, 3, 3, 3]);
  assert.equal(kindOf("Outlook"), "email");
});

test("the message connections carry it, a code host or a database does not", () => {
  assert.deepEqual(["whatsapp", "teams", "slack", "outlook", "gmail"].map(combines), [true, true, true, true, true]);
  assert.deepEqual(["github", "sqlite", "jira", ""].map(combines), [false, false, false, false]);
});

test("the ends are labelled Keep separate and Combine, and every level says what it does", () => {
  assert.equal(MARKS[0].label, "Keep separate"); assert.equal(MARKS.at(-1).label, "Combine");
  assert.deepEqual(MARKS.map((m) => m.value), [1, 2, 3, 4, 5]);
  for (const m of MARKS) assert.ok(SAYS[m.value]);
  assert.deepEqual([0, 1, 5, 6, "x"].map(clampLevel), [null, 1, 5, null, null]);
});

test("the card renders the slider in its inbound step, read from and saved to /api/combine/{kind} when let go", () => {
  assert.match(src, /\{combines\(conn\.Type\) && <CombineStep conn=\{conn\}/);
  assert.match(src, /<Slider[^>]*marks=\{MARKS\}[^>]*aria-label="Combine level"/s);
  assert.match(src, /api\.get\(`\/api\/combine\/\$\{kind\}`\)/);
  assert.match(src, /onChangeCommitted=\{\(_, v\) => save\(v\)\}/);
  assert.match(src, /api\.put\(`\/api\/combine\/\$\{kind\}`, \{ level: lv \}\)/);
});

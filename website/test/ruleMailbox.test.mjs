// Settings → Rules: "Applies to" - All mailboxes or one connected sending mailbox, offered only when there is a choice to make.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ALL_MAILBOXES, mailboxChoices, mailboxValue } from "../src/ruleMailbox.js";

const NW = { address: "alex@northwind.example" }, CT = { address: "alex@contoso.example" };

test("one mailbox, or none, offers no choice", () => {
  assert.deepEqual(mailboxChoices([]), []);
  assert.deepEqual(mailboxChoices([NW]), []);
  assert.deepEqual(mailboxChoices([NW, { address: "ALEX@northwind.example ".toLowerCase() }]), []);   // one address, twice
});

test("two mailboxes: All mailboxes first (blank, today's behaviour), then each", () => {
  assert.deepEqual(mailboxChoices([NW, CT]).map((o) => [o.value, o.label]),
    [["", ALL_MAILBOXES], ["alex@northwind.example", "alex@northwind.example"], ["alex@contoso.example", "alex@contoso.example"]]);
  assert.equal(mailboxValue(mailboxChoices([NW, CT]), undefined), "");
  assert.equal(mailboxValue(mailboxChoices([NW, CT]), "Alex@Contoso.example"), "alex@contoso.example");
});

test("a rule scoped to a mailbox no longer connected keeps it, said so", () => {
  const c = mailboxChoices([NW, CT], "ops@contoso.example");
  assert.deepEqual(c.at(-1), { value: "ops@contoso.example", label: "ops@contoso.example (not connected)" });
  assert.equal(mailboxValue(c, "ops@contoso.example"), "ops@contoso.example");
});

test("the rule editor draws it and saves it through the rule's own save", () => {
  const src = fs.readFileSync(path.join(process.cwd(), "src", "SettingsView.jsx"), "utf8");
  assert.match(src, /label="Applies to"/);
  assert.match(src, /setDraft\(\{ \.\.\.draft, Mailbox: e\.target\.value \}\)/);
  assert.match(src, /api\.get\("\/api\/mailboxes"\)/);
});

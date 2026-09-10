// The SimpleFIN card: a setup token pasted into a field, spent once by the server.
//
// Teller's card needs a script from cdn.teller.io, an application id and a certificate pair; this
// one needs a text field, which is the whole reason it exists - Teller stopped taking signups
// (2026-09-10) and a card nobody new can connect is not a card.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the card is offered in Markets & finance, ahead of the one nobody can sign up for", () => {
  const src = read("ConnectorsView.jsx");
  const group = src.match(/dataCards\(\["simplefin".*?\]\)/s);
  assert.ok(group, "simplefin should lead the Markets & finance data cards");
  assert.ok(group[0].indexOf("simplefin") < group[0].indexOf("teller"));
  assert.match(src, /simplefin: \{ title: "Bank & card feed \(SimpleFIN\)"/);
  for (const t of ["simplefin_accounts", "simplefin_transactions", "simplefin_balances", "simplefin_spend"]) {
    assert.ok(src.includes(t), t);
  }
});

test("connecting is a token in a field, claimed server-side, and never a browser widget", () => {
  const src = read("ConnectorsView.jsx");
  assert.match(src, /widget: "token"/);
  assert.match(src, /claim: \(cid\) => `\/api\/connectors\/\$\{cid\}\/simplefin\/claim`/);
  assert.match(src, /meta\.connect\.widget === "token"\) return await pasteToken\(\)/);
  // one-shot: the field is cleared on success only, so a rejected token can be corrected
  assert.match(src, /setToken\(""\); await load\(\); reload\(\)/);
  assert.doesNotMatch(src, /cdn\.simplefin/);
});

test("the four reports are buildable and named for the card they come from", () => {
  const src = read("ReportsView.jsx");
  assert.match(src, /simplefin_transactions: "Bank & card \(SimpleFIN\)/);
  assert.match(src, /simplefin_spend: "Bank & card \(SimpleFIN\)/);
  // no last four in this protocol: the account field must not ask for digits
  const field = src.match(/simplefin_transactions: \[\[(.*?)\]/s)[1];
  assert.ok(!/last four/i.test(field), field);
});

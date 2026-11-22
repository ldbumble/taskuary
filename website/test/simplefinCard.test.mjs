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


test("connecting is a token in a field, claimed server-side, and never a browser widget", () => {
  const src = read("ConnectorsView.jsx");
  assert.match(src, /widget: "token"/);
  assert.match(src, /claim: \(cid\) => `\/api\/connectors\/\$\{cid\}\/simplefin\/claim`/);
  assert.match(src, /meta\.connect\.widget === "token"\) return await pasteToken\(\)/);
  // one-shot: the field is cleared on success only, so a rejected token can be corrected
  assert.match(src, /setToken\(""\); await load\(\); reload\(\)/);
  assert.doesNotMatch(src, /cdn\.simplefin/);
});

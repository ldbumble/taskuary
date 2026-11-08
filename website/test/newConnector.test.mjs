import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { connectorNamed } from "../src/connectorCatalog.js";

// "i want to connect taskuary to linkedin" in New's agent job had no way to Connections (a tester, 2026-10-20): the card it names is
// offered on the row, read from the catalogue's own names.

test("the card a request names, by the catalogue's type or title", () => {
  assert.equal(connectorNamed("i want to connect taskuary to linkedin")?.type, "linkedin");
  assert.equal(connectorNamed("hook up my second Outlook")?.type, "outlook");
  assert.equal(connectorNamed("connect Slack please")?.type, "slack");
  assert.equal(connectorNamed("set up QuickBooks Online")?.type, "quickbooks");
  assert.equal(connectorNamed("set up quickbooks")?.type, "quickbooks");
});

test("no card for words that only share a fragment, and none for plain work", () => {
  assert.equal(connectorNamed("work out why the nightly export drops the last facility"), null);
  assert.equal(connectorNamed("put it online by friday"), null);
  assert.equal(connectorNamed("the slackers report"), null);
  assert.equal(connectorNamed(""), null);
});

test("a plain word the card's title writes in lower case names no card, its whole name still does", () => {
  assert.equal(connectorNamed("unzip notes.zip in Downloads and tell me what is on my screen"), null);
  assert.equal(connectorNamed("look through the database backups"), null);
  assert.equal(connectorNamed("set up a strategy screen")?.type, "screen");
  assert.equal(connectorNamed("connect teams")?.type, "teams");
});

test("New offers the card on its own row, beside the job, and the job still starts if pressed", () => {
  const src = readFileSync(new URL("../src/NewSheet.jsx", import.meta.url), "utf8");
  assert.ok(src.includes("useVerbs(`new-connect${me}`"));
  assert.ok(src.includes("openAppLink(`#connector=${named.type}`)"));
  assert.ok(src.includes("onWords={setText}"));
});

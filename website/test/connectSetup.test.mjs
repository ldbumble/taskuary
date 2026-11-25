// A card that needs a connection not set up brings that connection's own setup up under it (the owner, 2026-11-25): its Connect opened the
// Connections page and left the card behind. Which connection a Connect's link names - one card's own, never Email's section or a page.
import assert from "node:assert/strict";
import test from "node:test";
import { cardKind, setupType } from "../src/connectSetup.js";

test("a Connect that names one connection's card sets that card up under the card; any other link opens where it points", () => {
  assert.equal(setupType("#connector=intacct"), "intacct");
  assert.equal(setupType("#connector=LinkedIn"), "linkedin");
  for (const h of ["#connections&section=email", "#settings=images", "", null, "#connector=", "https://example.com/#connector=x"]) assert.equal(setupType(h), "", h);
});

// ...and the setup under the card is THAT connection's own kind of card, as the Connections page draws it: LinkedIn's Connect brought up the
// mail form (no fields, a greyed Connect) for a card whose setup is its keys, its Sign in with LinkedIn and its Test
test("the setup a card's Connect brings up is the card the Connections page draws for that type; only a mailbox gets the short form", () => {
  const tables = { data: { linkedin: {}, bluesky: {}, jira: {} }, tools: new Set(["notion_mcp"]) };
  for (const inline of [false, true]) {
    for (const t of ["linkedin", "bluesky", "jira"]) assert.equal(cardKind(t, tables, inline), "data", t);
    assert.equal(cardKind("notion_mcp", tables, inline), "tool");
    assert.equal(cardKind("mssql", tables, inline), "mssql");
    for (const t of ["slack", "telegram", "whatsapp"]) assert.equal(cardKind(t, tables, inline), "channel", t);
  }
  for (const t of ["outlook", "gmail", "imap"]) { assert.equal(cardKind(t, tables, true), "mail", t); assert.equal(cardKind(t, tables), "channel", t); }
});

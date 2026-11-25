// A card that needs a connection not set up brings that connection's own setup up under it (the owner, 2026-11-25): its Connect opened the
// Connections page and left the card behind. Which connection a Connect's link names - one card's own, never Email's section or a page.
import assert from "node:assert/strict";
import test from "node:test";
import { setupType } from "../src/connectSetup.js";

test("a Connect that names one connection's card sets that card up under the card; any other link opens where it points", () => {
  assert.equal(setupType("#connector=intacct"), "intacct");
  assert.equal(setupType("#connector=LinkedIn"), "linkedin");
  for (const h of ["#connections&section=email", "#settings=images", "", null, "#connector=", "https://example.com/#connector=x"]) assert.equal(setupType(h), "", h);
});

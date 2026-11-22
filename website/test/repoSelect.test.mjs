import test from "node:test";
import assert from "node:assert/strict";


import { namedRepo } from "../src/repoNames.js";
const rows = [{ repo: "northwind/ledger" }, { repo: "northwind/portal" }, { repo: "org/app" }];

test("the Start panel's repository follows the one the instruction names, as a whole word", () => {
  assert.equal(namedRepo(rows, "can you check this in ledger if this is happening?"), "northwind/ledger");
  assert.equal(namedRepo(rows, "look at northwind/portal."), "northwind/portal");
  assert.equal(namedRepo(rows, "the ledgers are off"), "");                  // not the word
  assert.equal(namedRepo(rows, "compare ledger with portal"), "");           // two named: the owner picks
  assert.equal(namedRepo(rows, "fix the app"), "");                          // too short a name to trust
});

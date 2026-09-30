import { taskSource } from "./taskSource.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { namedRepo } from "../src/repoNames.js";
const rows = [{ repo: "northwind/ledger" }, { repo: "northwind/portal" }, { repo: "org/app" }];

test("the Start panel's repository follows the one the instruction names, as a whole word", () => {
  assert.equal(namedRepo(rows, "can you check this in ledger if this is happening?"), "northwind/ledger");
  assert.equal(namedRepo(rows, "look at northwind/portal."), "northwind/portal");
  assert.equal(namedRepo(rows, "the ledgers are off"), "");                  // not the word
  assert.equal(namedRepo(rows, "compare ledger with portal"), "");           // two named: the owner picks
  assert.equal(namedRepo(rows, "fix the app"), "");                          // too short a name to trust
});

test("the Start panel shows the repository and pins it before the session starts", () => {
  const view = taskSource();
  assert.match(view, /<RepoSelect taskId=\{selected\}/);
  assert.match(view, /api\.put\(`\/api\/tasks\/\$\{id\}\/repo`, \{ repo: startRepo/);
  assert.match(view, /disabled=\{!!startingAgent \|\| startRepo === ""\}/);
});

test("both reply buttons spin and say Drafting while the AI writes the draft", () => {
  const view = taskSource();
  assert.equal((view.match(/\{openingReply \? "Drafting…" : replyPrimary\}/g) || []).length, 2);
  assert.match(view, /startIcon=\{openingReply \? <CircularProgress size=\{11\} \/>/);
});

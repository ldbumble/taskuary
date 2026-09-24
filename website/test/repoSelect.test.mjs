import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// namedRepo lives in RepoPicker.jsx; pull the pure function out of the source so the test needs no JSX loader
const src = readFileSync(fileURLToPath(new URL("../src/RepoPicker.jsx", import.meta.url)), "utf8");
const body = src.slice(src.indexOf("export const namedRepo"), src.indexOf("export const RepoSelect"));
const namedRepo = new Function(`${body.replace("export const namedRepo", "const namedRepo")}; return namedRepo;`)();
const rows = [{ repo: "northwind/ledger" }, { repo: "northwind/portal" }, { repo: "org/app" }];

test("the Start panel's repository follows the one the instruction names, as a whole word", () => {
  assert.equal(namedRepo(rows, "can you check this in ledger if this is happening?"), "northwind/ledger");
  assert.equal(namedRepo(rows, "look at northwind/portal."), "northwind/portal");
  assert.equal(namedRepo(rows, "the ledgers are off"), "");                  // not the word
  assert.equal(namedRepo(rows, "compare ledger with portal"), "");           // two named: the owner picks
  assert.equal(namedRepo(rows, "fix the app"), "");                          // too short a name to trust
});

test("the Start panel shows the repository and pins it before the session starts", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/TasksView.jsx", import.meta.url)), "utf8");
  assert.match(view, /<RepoSelect taskId=\{selected\}/);
  assert.match(view, /api\.put\(`\/api\/tasks\/\$\{id\}\/repo`, \{ repo: startRepo/);
  assert.match(view, /disabled=\{!!startingAgent \|\| startRepo === ""\}/);
});

test("both reply buttons spin and say Drafting while the AI writes the draft", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/TasksView.jsx", import.meta.url)), "utf8");
  assert.equal((view.match(/\{openingReply \? "Drafting…" : replyPrimary\}/g) || []).length, 2);
  assert.match(view, /startIcon=\{openingReply \? <CircularProgress size=\{11\} \/>/);
});

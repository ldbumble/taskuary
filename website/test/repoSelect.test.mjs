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
  // ...and with no coding tool chosen it stays off (owner-approved, 2026-10-21)
  assert.match(view, /disabled=\{!!startingAgent \|\| startRepo === "" \|\| runPics\.busy \|\| !agentsRead \|\| !codingReady\}/);
  // the picker above already names it: a second "repo · …" by Cancel said it twice (the owner, 2026-10-13)
  assert.doesNotMatch(view, /repo · \{repoOf\(t\)\}/);
});

test("the next-run box takes the mic and pictures like Continue, and both starts send what was typed with them", () => {
  const view = taskSource();
  const form = view.slice(view.indexOf("const nextRunForm = ("), view.indexOf("IN THE AGENT BOX, NOT UNDER THE CONVERSATION"));
  assert.match(form, /\{\.\.\.runPics\.drop\}/);
  assert.match(form, /<AttachImage pics=\{runPics\}/);
  assert.match(form, /<MicButton /);
  assert.match(form, /<ImageTray pics=\{runPics\}/);
  assert.match(view, /instructions: withImages\(run\.instruction\.trim\(\), runPics\.paths\)/);
  assert.match(view, /instruction: withImages\(run\.instruction\.trim\(\), runPics\.paths\)/);
});

test("both reply buttons spin and say Drafting while the AI writes the draft", () => {
  const view = taskSource();
  assert.equal((view.match(/\{openingReply \? "Drafting…" : replyPrimary\}/g) || []).length, 2);
  assert.match(view, /startIcon=\{openingReply \? <CircularProgress size=\{11\} \/>/);
});

// START CODING SESSION WITH NO REPOSITORY CHOSEN (the owner, 2026-11-06: "let's take repo decision out of the triage - remove it completely
// and then the use_repo tool to figure it out"): nothing chosen is no hold. The session opens in the task's own folder and the agent picks
// its checkout (repochoice.py); a repository the owner picks in the Start panel is still pinned first, and that pick wins.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const page = readFileSync(fileURLToPath(new URL("../src/TaskPage.jsx", import.meta.url)), "utf8");

test("Start coding session is not held for a repository - the agent picks one", () => {
  const at = page.indexOf('startingAgent === "coding" ? "Starting…" : btn("coding_agent")');
  assert.ok(at > 0);
  const start = page.slice(page.lastIndexOf("<Button", at), page.indexOf('choice("agent", "regular_agent")', at));
  assert.doesNotMatch(start, /startRepo === ""/, "an empty choice neither greys Start nor asks first");
  assert.doesNotMatch(start, /\{PICK_CODE\} first/);
  assert.match(page, /if \(startRepo\) await api\.put\(`\/api\/tasks\/\$\{id\}\/repo`/, "the owner's pick is pinned before the start");
});

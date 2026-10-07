// A GENERAL TASK IS NOT HANDED THE CODER (the owner, 2026-10-07: "we don't want coder profile always"). The picker filled a
// blank with the roster's first name - `coder` - and Send to agent sent it, which the dispatch refuses on a non-coding task
// (server.py: "is a coding profile - it cannot run a non-coding task"). Blank on a general task means "the profile it has".
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");

test("opening a general task picks its own role, or blank - never the roster's first name", () => {
  assert.match(src, /agent: agents\.includes\(owned\) \? owned : isGeneralKind\(task\.Kind\) \? "" : agents\[0\]/);
});

test("the roster check leaves a general task's blank alone", () => {
  assert.match(src, /!agents\.includes\(run\.agent\) && !\(generalTask && !run\.agent\)/);
});

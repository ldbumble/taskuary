// A GENERAL TASK IS NOT HANDED THE CODING PROFILE (the owner, 2026-10-07: not the coding profile every time). The picker
// filled a blank with the roster's first name - the coding profile - and Send to agent sent it, which the dispatch refuses on a
// non-coding task (server.py: "is a coding profile - it cannot run a non-coding task"). Blank on a general task means "the
// profile it has"; a coding task takes the profile of KIND coding, never a name (2026-10-15: no profile is special by its name).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");

test("opening a general task picks its own role, or blank - never the roster's first name", () => {
  // ...and nor is any task when no coding tool is connected: the general agent is the only one there is (B3)
  assert.match(src, /agent: agents\.includes\(owned\) \? owned : opensOnRegular\(task\.Kind\) \|\| !canCode \? "" : codingProfile\(agents, kinds\)/);
  assert.doesNotMatch(src, /agents\[0\]/);
});

test("the roster check leaves a general task's blank alone", () => {
  // ...and a hand-off's on any task: blank there is "its own profile", not a gap for researcher to fill (2026-10-15)
  assert.match(src, /!agents\.includes\(run\.agent\) && !\(\(generalTask \|\| handOff \|\| !canCode\) && !run\.agent\)/);
});

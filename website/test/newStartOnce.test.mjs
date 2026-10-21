import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// A REFUSED START FILES ONE TASK (the UI audit, 2026-10-21): New > Give an agent a job made the task, then asked for the start; a
// refused start said "nothing started" while a task stood filed, and every retry filed another copy
const src = readFileSync(new URL("../src/NewSheet.jsx", import.meta.url), "utf8");
const agent = src.slice(src.indexOf('} else if (kind === "agent") {'), src.indexOf('} else if (kind === "goal") {'));

test("the same words pressed again start the task already filed, never a second one", () => {
  assert.match(agent, /const again = filed\.current\?\.about === about && filed\.current\.how === how \? filed\.current : null;/);
  assert.match(agent, /const data = again \|\| \(await api\.post\("\/api\/tasks"/);
  assert.match(agent, /if \(!again\) \{\s+filed\.current = \{ \.\.\.data, about, how \};/);
  assert.ok(agent.indexOf("filed.current = null;") > agent.indexOf("/dispatch"), "forgotten only once a start went through");
});

test("a refused start names the task it filed", () => {
  assert.match(agent, /\$\{data\.ref\} is filed but did not start - /);
  assert.equal((agent.match(/\/dispatch`/g) || []).length, 1, "one start, for both kinds of agent");
});

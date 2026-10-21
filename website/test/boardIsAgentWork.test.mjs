import { taskSource } from "./taskSource.mjs";
import { KIND_OPTIONS } from "../src/kinds.js";
import { LANE_META, LEVEL_META } from "../src/funnelPile.js";
/* The Board is the agent floor.
 *
 * "board is only for things that hit agents correct? it should not take up our agent capactity"
 * (the owner, 2026-09-10). A `reply` is drafted by the same model triage uses - it never opens a
 * session and never queues for a slot - and a `task` is the owner's own list with nothing working
 * it. Both belong in Tasks and in Review, and a card for either on the floor is a worker that does
 * not exist.
 *
 * Capacity was never the bug: the cap gate lives in the coding/general dispatch paths, and on the
 * owner's own store there were zero worker sessions against any reply task. Visibility was.
 */
import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { isAgentKind, NO_AGENT_KINDS } from "../src/autostart.js";

const src = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("only work an agent runs counts as agent work", () => {
  for (const kind of ["coding", "general", "research", "marketing"]) {
    assert.equal(isAgentKind(kind), true, `${kind} is agent work`);
  }
  for (const kind of ["reply", "task", "setup"]) {
    assert.equal(isAgentKind(kind), false, `${kind} never reaches a session`);
  }
});

test("an unknown kind keeps its card - the rule fails open", () => {
  // hiding a card is worse than showing one: a kind nobody has thought of yet must not vanish
  // from the one screen meant to show everything running.
  assert.equal(isAgentKind("something-new"), true);
  assert.equal(isAgentKind(""), true);
  assert.equal(isAgentKind(undefined), true);
  assert.ok(!NO_AGENT_KINDS.has("coding"));
});

test("the columns filter by it", () => {     // the Studio was removed (2026-10-15); the Game reads studioModel.js
  for (const file of ["BoardView.jsx"]) {
    const text = src(file);
    assert.match(text, /isAgentKind/, `${file} does not filter by kind`);
    assert.match(text, /from "\.\/autostart\.js"/, `${file} does not import the rule`);
  }
});

test("the wall is deliberately NOT filtered", () => {
  // its cards come from /api/terminals - live sessions - and the task list is only the lookup that
  // gives one its title. Filtering it would strip the name off a session started by hand.
  const text = src("WallView.jsx");
  assert.doesNotMatch(text, /isAgentKind/);
  assert.match(text, /NOT filtered by kind/, "the reason it is exempt has to be written down");
});

test("every task row says who works it, in the owner's words", () => {
  // ...read from kinds.json through kinds.js by both halves of the tab (the cleanup round, 2026-10-18)
  const text = taskSource();
  for (const label of ["your task", "agent · general", "agent · coding", "reply"]) {
    assert.ok(KIND_OPTIONS.some((o) => o.label === label), `the kind vocabulary is missing ${label}`);
  }
  assert.equal(text.match(/from "\.\/kinds\.js"/g)?.length, 2, "the list and the task page both read kinds.js");
  // the work rail's heading for band 2 is "tasks" since 2026-10-21 - every open task, an agent on it or not; a row with nobody on it
  // still says "on you" (lanes.json `yours`), which is what the heading no longer says for it
  assert.equal(LEVEL_META.task.word, "tasks", "the rail's band-2 heading is not 'tasks'");
  assert.equal(LANE_META.yours.word, "on you");
});

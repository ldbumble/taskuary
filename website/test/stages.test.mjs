// THE ONE STAGE MODEL (taskuary/stages.json, the owner 2026-10-26: "are these modes defined well anywhere besides the UI ... we should
// define this well"): the page, the server and the Assistant read one file - its stages, their parts and the rules' order
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { RULES, STAGE, drawerLit, mainView, stageFrom, stageOf } from "../src/stages.js";
import { VERBS } from "../src/buttons.js";

test("every stage names its parts, and every move is a button by its one name", () => {
  for (const [k, s] of Object.entries(STAGE)) {
    assert.ok(["task", "work"].includes(s.main), `${k}: main`);
    assert.ok(s.shows && s.drawer && s.word, `${k}: shows, drawer, word`);
    assert.equal(typeof s.lit, "boolean", `${k}: lit`);
    assert.ok([null, "main", "drawer"].includes(s.advisor), `${k}: advisor`);
    // the Advisor stands over the work where the work is the page, in the right drawer where the task is
    if (s.advisor) assert.equal(s.advisor, s.main === "work" ? "main" : "drawer", k);
    assert.ok(s.verbs.length && s.verbs.every((v) => v in VERBS), `${k}: verbs`);
    // a lit tab is the right drawer's: only where the task is the page
    if (s.lit) assert.equal(s.main, "task", k);
  }
  assert.ok(RULES.every(([, st]) => st in STAGE), "every rule names a stage");
  assert.equal(RULES.at(-1)[0], null, "the last rule always holds");
});

test("the rules go in their order - the first fact that holds wins", () => {
  assert.equal(stageFrom({}), "to_start");
  assert.equal(stageFrom({ live: true, closed: true }), "agent_working", "a done task continued is work in progress again");
  assert.equal(stageFrom({ closed: true, drafted: true, result: true }), "done");
  assert.equal(stageFrom({ drafted: true, result: true }), "close_out", "a draft under a Result: Close out is the move");
  assert.equal(stageFrom({ owed: true, list: true }), "to_reply");
});

// THE PAGE'S OWN READING: what it draws makes the stage, and the stage gives the same main view and lit tab the page had before it
const OLD_MAIN = ({ sessionView = false, stacked = false, focus = null, drafted = false }) =>
  sessionView ? "work" : stacked ? null : focus === "agent" || (focus === "reply" && drafted) || focus === null ? "work" : "task";
const OLD_LIT = ({ main, focus }) => main === "task" && (focus === "reply" || focus === "source");
test("the page's stage keeps every open task's main view and lit tab", () => {
  for (const focus of [null, "none", "agent", "reply", "list", "source"])
    for (const drafted of [false, true]) for (const sessionView of [false, true]) for (const stacked of [false, true]) {
      const stage = stageOf({ focus, drafted }), main = mainView({ stage, sessionView, stacked });
      assert.equal(main, OLD_MAIN({ sessionView, stacked, focus, drafted }), JSON.stringify({ focus, drafted, sessionView, stacked }));
      assert.equal(drawerLit({ main, stage }), OLD_LIT({ main, focus }), JSON.stringify({ focus, drafted }));
    }
  assert.equal(stageOf({ focus: null }), "agent_working");
  assert.equal(stageOf({ focus: "none" }), "waiting");
  assert.equal(stageOf({ focus: "agent" }), "agent_result");
  assert.equal(stageOf({ focus: "reply", drafted: true }), "close_out");
  assert.equal(stageOf({ focus: "reply" }), "to_reply");
  assert.equal(stageOf({ focus: "list" }), "todo");
  assert.equal(stageOf({ focus: "source" }), "to_start");
});

// ...the one change (2026-10-26): a CLOSED task is `done` and opens on how it closed - a removed task nobody worked opened on its ask
test("a closed task is done, opens on how it closed, and has no Advisor section", () => {
  for (const focus of ["agent", "reply", "list", "source"]) {
    const stage = stageOf({ focus, drafted: true, closed: true });
    assert.equal(stage, "done");
    assert.equal(mainView({ stage }), "work");
  }
  assert.equal(STAGE.done.advisor, null);
  assert.equal(stageOf({ focus: null, closed: true }), "agent_working", "a session continued on it");
});

test("the task page reads the stage, and says it on its body", () => {
  const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /import \{ drawerLit, mainView, stageOf \} from "\.\/stages\.js";/);
  // ...read through the held view (2026-10-27: Send must not swap Close out for the task): the stage's view, held once open
  assert.match(page, /const mainNow = mainView\(\{ stage: taskStage, sessionView, stacked \}\);/);
  assert.match(page, /const main = mainHeld\.current\.main;/);
  assert.match(page, /data-tq-stage=\{taskStage\}/);
});

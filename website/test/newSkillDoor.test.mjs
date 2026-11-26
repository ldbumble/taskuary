// A SKILL HAS ITS OWN DOORS (the owner, 2026-10-22: "this is not skill ui? ... no new skill ui either??"): New has a Skill
// tab beside Report and Workflow, Reports has + New skill beside + New report and + New workflow, and both open the one road to a
// skill there is - the Skills shelf's New skill dialog (NewSkillDialog), with the words New was given.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canvasRequestFromHash } from "../src/canvasLinks.js";
import { NEW_PB, askSkill, takeSkillAsk } from "../src/skillOpen.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");


test("New's link lands on the Skills shelf with New skill asked for - each ask numbered, so a second opens it again", () => {
  assert.equal(NEW_PB, "new-skill");
  assert.deepEqual(canvasRequestFromHash(`#report=${NEW_PB}`, 4).state, { section: "skills", open: null, newPb: 5 });
  assert.deepEqual(canvasRequestFromHash("#report=skills").state, { section: "skills", open: null });
  // ...and About you's link of the few hours it held them (2026-11-06) lands on Reports too
  assert.deepEqual(canvasRequestFromHash(`#about=${NEW_PB}`, 4), { kind: "browse", area: "reports", state: { section: "skills", open: null, newPb: 5 }, n: 4 });
});

test("the words wait for the shelf and are taken once; the dialog starts from them only when Set up with AI was pressed on New", () => {
  askSkill("when Erin asks for the weekly numbers, gather them for my review", true);
  assert.deepEqual(takeSkillAsk(), { text: "when Erin asks for the weekly numbers, gather them for my review", start: true });
  assert.equal(takeSkillAsk(), null);
  const shelf = read("SkillShelf.jsx"), dlg = read("NewSkillDialog.jsx");
  assert.match(shelf, /initialText=\{ask\?\.text \|\| ""\} autoStart=\{!!ask\?\.start\}/);
  assert.match(dlg, /useState\(initialText\.trim\(\) \? "scratch" : ""\)/);
  // ...and it builds right there (taskuary/build.py): the strip, started with the words, opens the skill once it is saved
  assert.match(dlg, /useState\(autoStart && !!initialText\.trim\(\)\)/);
  assert.match(dlg, /<SetupWithAi kind="skill"[\s\S]{0,260}auto\s+onDone=\{\(v\) => \{ onClose\?\.\(\); openAppLink\(v\.link\); \}\} \/>/);
});

import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");

test("an uncertain task repo opens the chooser and resumes the attempted launch", () => {
  const tasks = src("TasksView.jsx");
  assert.match(tasks, /could not tell which checkout/);
  assert.match(tasks, /setResumeAfterRepo\(body\)/);
  assert.match(tasks, /openTerm\(\{ \.\.\.launch, repo: data\.repo, cwd: null \}\)/);
});

test("the Assistant card asks for a repo and retries dispatch after the choice", () => {
  const cards = src("assistantCards.jsx");
  assert.match(cards, /data\.dispatch === "needs_repo"/);
  assert.match(cards, /Which repository should the coding agent use\?/);
  assert.match(cards, /setRepoAsk\(null\); startAgent\("coding"\)/);
});

test("a selected repository with no local checkout still offers path setup", () => {
  const picker = src("RepoPicker.jsx");
  assert.match(picker, /on && r\.has_path/);
  assert.match(picker, /on \? "set path" : "use this"/);
});

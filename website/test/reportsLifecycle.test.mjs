import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../src/ReportsView.jsx", import.meta.url), "utf8");

test("Run now is owned by the server and survives leaving the Reports tab", () => {
  const start = source.indexOf("const runNow = async (sid)");
  const block = source.slice(start, source.indexOf("const syncNow", start));
  assert.match(block, /\/api\/reports\/\$\{sid\}\/rerun/);
  assert.doesNotMatch(block, /\/api\/sources\/\$\{sid\}\/run/);
  assert.match(block, /running in the background/);
  assert.match(block, /leave this tab/);
});

test("an existing report has a visible top-level Delete button", () => {
  const wizard = source.slice(source.indexOf("function ReportWizard"));
  const header = wizard.slice(wizard.indexOf("return ("), wizard.indexOf("<Stepper"));
  assert.match(header, /Delete \{workflow \? "workflow" : "report"\}/);
  assert.match(header, /setConfirmDel\(true\)/);
  assert.match(wizard, /api\.delete\(`\/api\/sources\/\$\{cur\.SourceId\}`\)/);
});

test("one question decides whether a run reaches you at all", () => {
  // It used to be two panels, neither of which governed the TIMELINE - so a monitor that found
  // nothing still posted "All clear" every hour, and the only way to get that line was to ask the
  // model for it in the prompt, which is what made it post one (the owner, 2026-09-17: "if no
  // errors then don't show up at all ... make this better for all use cases").
  const panel = source.slice(source.indexOf("WHEN SHOULD THIS REACH YOU?"), source.indexOf("MOVE IT UP IF"));
  assert.match(panel, /\["always", "every run"\], \["wrong", "only when something is wrong"\], \["rule", "only when/);
  assert.match(panel, /AND ALSO TELL ME ON \(OPTIONAL\)/);
  assert.doesNotMatch(source, /TELL ME WHEN IT LOOKS WRONG/);        // the old panel, replaced not added to
  // the push is a destination on the same rule, so turning it off keeps the rule itself
  assert.match(panel, /cfg\.alert\?\.when \? \{ when: cfg\.alert\.when, count: cfg\.alert\.count, text: cfg\.alert\.text \} : undefined/);
});

test("the reading of an absent setting is the server's own, and prose is offered words", () => {
  // reports.reach_of does exactly this: a condition was the only way to ask for quiet, and an
  // assistant check was quiet already. If these two ever disagree the setup screen lies about
  // what the report will do.
  assert.match(source, /export const reachOf = \(c\) => \(\["always", "wrong", "rule"\]\.includes\(c\?\.reach\) \? c\.reach/);
  assert.match(source, /c\?\.alert\?\.when \? "rule" : c\?\.type === "assistant" \? "wrong" : "always"/);
  // "fewer rows than 5" on an AI summary compared five LINES, so a prose check is not offered it
  assert.match(source, /export const answersInProse = \(c\) => c\?\.type === "assistant" \|\| !!c\?\.ai_prompt/);
  const conditions = source.slice(source.indexOf("const CONDITIONS = ["), source.indexOf("];", source.indexOf("const CONDITIONS = [")));
  for (const row of ["fewer_than", "more_than"]) {
    const line = conditions.split("\n").find((l) => l.includes(row));
    assert.ok(line && !line.includes("prose:"), `${row} must not be offered to a check that answers in prose`);
  }
  assert.match(conditions, /v: "something_came_back", rows: "anything came back", prose: "it found something"/);
});

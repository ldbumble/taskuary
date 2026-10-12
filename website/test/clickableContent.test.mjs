import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("task and attachment actions use keyboard-operable buttons", () => {
  const wall = read("AgentWall.jsx");
  const attachments = read("Attachments.jsx");
  const taskPage = read("TaskPage.jsx");
  const learned = read("LearnedView.jsx");

  assert.match(wall, /<Typography component="button" type="button"[^>]+onClick=\{\(\) => onOpenTask\?\.\(n\.TaskId\)\}/);
  assert.match(attachments, /<Typography variant="caption" component="button" type="button"[^>]+onClick=\{fetchNow\}/);
  assert.match(attachments, /<Box key=\{a\.id\} component="button" type="button"[^>]+onClick=\{\(\) => setBig\(a\)\}/);
  assert.match(taskPage, /<Box component="button" type="button" onClick=\{\(\) => \{ const next = diffScope === "task" \? "checkout" : "task";/);
  assert.match(learned, /<button\s+type="button"\s+aria-expanded=\{looseOpen\}\s+onClick=\{\(\) => setLooseOpen\(\(o\) => !o\)\}/);
});

test("learned view loose verdicts disclosure uses a keyboard-operable button with aria-expanded", () => {
  const learned = read("LearnedView.jsx");

  // Initial state is collapsed (false)
  assert.match(learned, /const\s+\[looseOpen,\s*setLooseOpen\]\s*=\s*useState\(false\);/, "initial state must be collapsed (false)");

  // Disclosure control is a native <button type="button"> with aria-expanded bound to looseOpen
  const buttonMatch = learned.match(/<button\b[\s\S]*?<\/button>/);
  assert.ok(buttonMatch, "disclosure control must be a native <button>");
  const button = buttonMatch[0];

  assert.match(button, /\btype="button"/, "button type must be 'button'");
  assert.match(button, /\baria-expanded=\{looseOpen\}/, "button must bind aria-expanded to looseOpen");
  assert.match(button, /onClick=\{\(\) => setLooseOpen\(\(o\) => !o\)\}/, "button click must toggle looseOpen");

  // Accessible name includes the meaningful disclosure label
  assert.match(button, /VERDICTS NOT YET IN ANY LINE/, "button must include the disclosure label");

  // Controlled disclosure content is shown only when expanded
  assert.match(learned, /\{looseOpen\s*&&\s*\(/, "content grid must be conditionally rendered based on looseOpen");

  // Toggle state contract: collapsed (false) -> expanded (true) -> collapsed (false)
  let state = false;
  const toggle = (setter) => { state = setter(state); };
  toggle((o) => !o);
  assert.equal(state, true, "activating disclosure toggles state to expanded (true)");
  toggle((o) => !o);
  assert.equal(state, false, "activating disclosure again toggles state to collapsed (false)");
});

// "if no cli tool like cloud api tools no coding" (the owner, 2026-10-16): every screen that offers coding asks the server
// whether a coding tool is connected (capabilities.js) and offers nothing when none is.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the capability is asked once, re-asked when setup moves, and shows coding until the answer is in", () => {
  const c = read("capabilities.js");
  assert.match(c, /api\.get\("\/api\/capabilities"\)/);
  assert.match(c, /useState\(true\)/);
  assert.match(c, /tq-setup-changed/);
});

test("no coding tool: no Coding agent button, no coding kind to pick, no Coding agent settings", () => {
  assert.match(read("ui.jsx"), /\{canCode && <Button size="small" variant=\{agentKind === "coding"/);
  assert.match(read("ui.jsx"), /const suggestedKind = canCode && /);
  assert.match(read("assistantCards.jsx"), /i\.mid && !i\.tid && canCode && <Button[^\n]*propose\("coding_agent"/);
  assert.match(read("TaskPage.jsx"), /\.filter\(\(o\) => o\.key !== "coding" \|\| canCode \|\| t\.Kind === "coding"\)/);
  assert.match(read("TasksView.jsx"), /o\.made !== false && \(o\.key !== "coding" \|\| canCode\)/);
  assert.match(read("SettingsView.jsx"), /g !== "Coding agent" \|\| canCode/);
});

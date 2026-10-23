// "if no cli tool like cloud api tools no coding" (the owner, 2026-10-16): every screen that offers coding asks the server
// whether a coding tool is connected (capabilities.js) and offers nothing when none is.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the capability is asked once, re-asked when setup moves, and shows coding until the answer is in", () => {
  const c = read("capabilities.js");
  assert.match(c, /api\.get\("\/api\/capabilities"\)/);
  assert.match(c, /export const ASSUMED = \{ coding: true, ai: true, mail: true, send: \{\}, known: false \};/, "until the answer is in, everything shows");
  assert.match(c, /tq-setup-changed/);
  assert.match(c, /onLive\(\["feed-changed", "task-changed"\]/, "and re-read when the live feed says something changed");
  // every screen reads the one hook - no screen keeps its own coding check
  for (const f of ["ui.jsx", "assistantCards.jsx", "TaskPage.jsx", "TasksView.jsx", "SettingsView.jsx", "AssistantView.jsx"])
    assert.match(read(f), /useCapabilities\(\)/, f);
});

test("a channel the server names as unable to send hides its Send; one it does not name can send", async () => {
  // capabilities.js imports the page's api client; the pure rule is read from its source
  const c = read("capabilities.js");
  assert.match(c, /export const canSend = \(caps, channel\) => !channel \|\| caps\?\.send\?\.\[String\(channel\)\.toLowerCase\(\)\] !== false;/);
});

test("no coding tool: no Coding agent button, no coding kind to pick, no Coding agent settings", () => {
  assert.match(read("ui.jsx"), /\{canCode && <Button size="small" variant=\{agentKind === "coding"/);
  assert.match(read("ui.jsx"), /const suggestedKind = canCode && /);
  assert.match(read("assistantCards.jsx"), /i\.mid && !i\.tid && canCode && <Button[^\n]*setAsking\(\{ key: i\.key, coding: true \}\)/);
  assert.match(read("TaskPage.jsx"), /\.filter\(\(o\) => o\.key !== "coding" \|\| canCode \|\| t\.Kind === "coding"\)/);
  assert.match(read("TasksView.jsx"), /o\.made !== false && \(o\.key !== "coding" \|\| canCode\)/);
  assert.match(read("SettingsView.jsx"), /g !== "Coding agent" \|\| canCode/);
});

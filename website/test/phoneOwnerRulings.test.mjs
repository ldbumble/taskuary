// The owner's 2026-10-22 ruling that reaches the desktop's Settings: a walk-only phone chat keeps listening after a walk comes back (A5).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");

test("the walk-only listening choice says the chat keeps listening after a hand-back", () => {
  const s = src("SettingsView.jsx");
  assert.doesNotMatch(s, /listens only while a walk is handed over/);
  assert.match(s, /<MenuItem value="walk"[^>]*>listens once a walk is handed over, and after it comes back<\/MenuItem>/);
  assert.match(s, /Once a walk comes back, that chat keeps listening/);
});

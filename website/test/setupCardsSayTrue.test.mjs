import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// SETUP'S AI CARDS SAY WHAT IS TRUE (the UI audit, 2026-10-21): a CLI that failed its test read "Connected", and while ChatGPT's
// sign-in ran the line still said the last card's failure, as if ChatGPT had failed
const src = readFileSync(new URL("../src/FirstRun.jsx", import.meta.url), "utf8");

test("a CLI that failed its test says so, unlit, before any Connected", () => {
  const at = src.indexOf("const stateOf = (ai) =>"), body = src.slice(at, src.indexOf("const cliCards", at));
  assert.match(body, /ai\.failed && ai\.installed \? \["off", "Didn't pass the test - pick it to try again"\]/);
  assert.ok(body.indexOf("ai.failed") < body.indexOf("ai.connected ?"), "failed wins over connected");
});

test("a sign-in that is running says its own line over an older failure", () => {
  assert.match(src, /ai: \(signing \? "Finish signing in to ChatGPT[^"]*" : ""\) \|\| \(!browse && fix\?\.why\) \|\|/);
});

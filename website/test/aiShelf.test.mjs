// Setup's "What AI do you have?" kept its own copy of the Connections AI shelf, and Google Vertex AI and Meta landed on the shelf only
// (the owner, 2026-10-15: "google vertex ai does not show up like in the connection tab why are some missing?"). One list now.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { AI_SHELF, AI_WHY, SETUP_AI } from "../src/aiShelf.js";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("setup offers every AI on the Connections shelf that can sort mail", () => {
  assert.ok(SETUP_AI.includes("vertex_ai") && SETUP_AI.includes("meta"));
  assert.deepEqual(AI_SHELF.filter((t) => !SETUP_AI.includes(t)), ["chatgpt", "typesafe"]);
});

test("both screens read the one list and neither keeps its own", () => {
  assert.match(src("ConnectorsView.jsx"), /channelCards\(AI_SHELF\)/);
  assert.match(src("FirstRun.jsx"), /byType\(SETUP_AI\)/);
  assert.doesNotMatch(src("FirstRun.jsx"), /const AI_TYPES/);
});

test("every key card on setup's shelf says in one line what it is", () => {
  for (const t of SETUP_AI) assert.ok(AI_WHY[t] && AI_WHY[t].length < 60, t);
  assert.match(src("FirstRun.jsx"), /AI_WHY\[c\.Type\]/);
});

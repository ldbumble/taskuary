// THE "WHICH AI DOES WHAT" PAGE NAMES WHAT RUNS (the owner, 2026-11-11: "what is the cards ai on top? settings are not clear ... we still
// have drafting which the agent does now ... where is general agent??"): a level left on Default names the AI and model it resolves to,
// a card's RUNS line is the router's answer, choosing the AI already shown counts as choosing, and no Drafting card is drawn.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { levelDefault, levelModel, repick, runsLine } from "../src/aiCards.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const D = { general: { pick: "cli:codex", brain: "OpenAI Codex CLI", quick: "gpt-5.5, low effort", normal: "gpt-5.5", hard: "gpt-5.5, high effort" },
  coding: { pick: "cli:codex", brain: "OpenAI Codex CLI" } };

test("a level left on Default names the AI it resolves to, and its model box the model that runs", () => {
  assert.equal(levelDefault(D), "Default - OpenAI Codex CLI, set on its card below");
  assert.equal(levelDefault({ ...D, coding: { pick: "cli:claude", brain: "Claude Code" } }), "Default - OpenAI Codex CLI (coding: Claude Code), set on its card below");
  assert.equal(levelModel(D, null, "quick"), "gpt-5.5, low effort");
  assert.equal(levelModel(D, { runs: { hard: "opus" } }, "hard"), "opus");
  const rr = read("RouteRules.jsx");
  for (const gone of ["the card's AI\"", "\"its own model\"", "Triage, drafting"]) assert.ok(!rr.includes(gone), gone);
  assert.ok(rr.includes("{levelDefault(p.default)}"));
});

test("a card's RUNS line is the router's answer, and re-choosing the AI it shows is a choice while nobody made one", () => {
  assert.equal(runsLine({ runs: { brain: "Claude Code", model: "opus" } }), "Claude Code · opus");
  assert.equal(runsLine({ runs: { brain: "", model: "" } }), "nothing yet");
  assert.equal(repick({ chosen: false, value: "cli:codex" }, "cli:codex"), true);
  assert.equal(repick({ chosen: true, value: "cli:codex" }, "cli:codex"), false);
  assert.equal(repick({ chosen: false, value: "cli:codex" }, "cli:claude"), false);      // another value is the Select's own change
  const ai = read("AiDefaults.jsx");
  assert.ok(ai.includes("onClick={() => repick(slot, o.value) && onSave({ value: o.value })}"));
  assert.ok(!ai.includes("draft_ai") && !ai.includes("which brain"));
});

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

// rendered with two CLIs connected (2026-11-11): "Claude Code · quick: haiku · normal: ..." stood right over three "right now" rows saying
// the same three facts; and with that AI resting and nothing to take its work, the rows named it with no word that it rests
test("the routing card says each fact once: no line of levels the rows repeat, and a reason all three rows share stands once under them", async () => {
  const { levelLines, nowRows, sharedWhy } = await import("../src/aiCards.js");
  const claude = { pick: "cli:claude", brain: "Claude Code", quick: "haiku", normal: "opus", hard: "opus, high effort" };
  const now = ["quick", "normal", "hard"].map((level) => ({ level, pick: claude.pick, brain: claude.brain, model: claude[level], why: "" }));
  assert.deepEqual(levelLines({ levels: [claude], now }), [], "the rows already say it");
  const moved = now.map((n) => (n.level === "hard" ? { ...n, pick: "cli:codex", brain: "OpenAI Codex CLI", model: "gpt-5.4", why: "set for hard work" } : n));
  // ...a level that runs elsewhere right now (decided 2026-11-12): the card AI's own line read "Claude Code · quick: OpenAI Codex CLI, ..." -
  // the rows say which AI and model each level is on, so the line goes; another AI's line, with no row of its own, stays
  assert.deepEqual(levelLines({ levels: [claude], now: moved }), [], "the card AI's line goes where a level runs elsewhere");
  const gem = { pick: "cli:gemini", brain: "Gemini CLI", quick: "flash", normal: "pro", hard: "pro" };
  assert.deepEqual(levelLines({ levels: [claude, gem], now: moved }), [gem], "an AI no row is on keeps its line");
  assert.deepEqual(levelLines({ levels: [claude], now: [] }), [claude], "and with no rows the line is all there is");
  assert.deepEqual(nowRows(moved).map((n) => n.why), ["", "", "set for hard work"], "a row's own reason stays under it");
  const rest = now.map((n) => ({ ...n, why: "Claude Code is limited until 14:05" }));
  assert.equal(sharedWhy(rest), "Claude Code is limited until 14:05");
  assert.deepEqual(nowRows(rest).map((n) => [n.level, n.why]), [["quick", ""], ["normal", ""], ["hard", ""]], "said once, under the three");
  const same = now.map((n) => ({ ...n, model: "opus", why: "Claude Code is limited until 14:05" }));
  assert.deepEqual(nowRows(same).map((n) => [n.level, n.why]), [["every level", "Claude Code is limited until 14:05"]], "one row keeps its own reason");
  assert.equal(sharedWhy(same), "");
  const rr = read("RouteRules.jsx");
  assert.ok(rr.includes("{levelLines(p).map((l) => (") && rr.includes("{nowRows(p.now).map((n) => (") && rr.includes("{sharedWhy(p.now)}"));
});

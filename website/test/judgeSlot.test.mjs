// The fifth card offers a model that answers but cannot speak. The other four must never see it:
// AI_TYPES keeps it out of /api/brains on the server, and this keeps the page from putting it back.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the judge slot offers the decision model, and the other four never do", () => {
  const panel = read("AiDefaults.jsx");
  assert.match(panel, /judge_ai/);
  assert.match(panel, /judge_options/);
  // the decision model reaches exactly one picker: every other slot still reads `brains`
  const slot = panel.slice(panel.indexOf("const Slot"), panel.indexOf("export default"));
  assert.match(slot, /slot\.key === "judge_ai"/);
});

test("the judge picker does not offer auto twice", () => {
  // `brains` leads with an auto entry whose value is "", which is exactly what the judge's own
  // "the report's own brain" means - two rows that do the same thing read as a choice.
  const panel = read("AiDefaults.jsx");
  const slot = panel.slice(panel.indexOf("const Slot"), panel.indexOf("export default"));
  assert.match(slot, /brains\s*\|\|\s*\[\]\)\.filter\(\(o\) => o\.value\)/);
});

test("there is a card to paste the key on, and it says what it is for", () => {
  // Seeding the connector server-side is not enough: Connections renders from its own catalog and
  // names the AI cards explicitly, so a card left out of both lists is a key with nowhere to go.
  const view = read("ConnectorsView.jsx");
  assert.match(view, /^ {2}typesafe: \{ group: "AI — agents & models"/m);
  // the list spans lines now that nine OpenAI-compatible providers joined it, so match it
  // whole rather than end-to-end on one line
  const named = view.slice(view.indexOf('channelCards(["anthropic"'), view.indexOf('catalogCards("AI'));
  assert.match(named, /"typesafe"/);
  assert.match(view, /Where runs go/);          // where it is picked, said on the card itself
});

test("the slot with no model of its own does not show a model box", () => {
  const panel = read("AiDefaults.jsx");
  const slot = panel.slice(panel.indexOf("const Slot"), panel.indexOf("export default"));
  assert.match(slot, /!isJudge && \(/);
});

// A rule you cannot read is a rule you cannot trust, and this slot IS four questions. It is also the
// one slot where the thing answering may not be a chat model at all - so the card that shows "the
// prompt" has to show what is actually sent (the owner, 2026-09-17: "show the wording for jev ...
// what are the decision choices it's going for").
test("the Where runs go card lists what it is asked", () => {
  const panel = read("AiDefaults.jsx");
  assert.match(panel, /ASKED OF IT, ONCE PER RUN/);
  assert.match(panel, /slot\.decides/);
  assert.match(panel, /slot\.evidence/);
});

test("a decision model is shown its typed questions, not a prompt it never gets", () => {
  const view = read("ReportsView.jsx");
  assert.match(view, /export const judgeQuestions/);
  assert.match(view, /judge\?\.kind === "decision" \? judgeQuestions\(cfg, shown\) : judgePrompt\(cfg, shown\)/);
  // ...and the two sides of the judgement are both written out, with the threshold said out loud
  assert.match(view, /yes:   \$\{routeOf\(c, l\)\[1\]\}/);
  assert.match(view, /no:    \$\{JEV_FALSE\}/);
  assert.match(view, /≥ 0\.50 is yes/);
});

test("the strings the card shows are the strings the server sends", () => {
  // the same contract PROMPT_SAYS has with reports.LINE_SAYS: a paraphrase here is a lie on screen
  const view = read("ReportsView.jsx");
  const jev = readFileSync(fileURLToPath(new URL("../../taskuary/jev.py", import.meta.url)), "utf8");
  const reports = readFileSync(fileURLToPath(new URL("../../taskuary/reports.py", import.meta.url)), "utf8");
  const falseText = /FALSE = '([^']+)'/.exec(jev)[1];
  const evidence = /EVIDENCE_RULE = \('([^']+)'\s*\n\s*'([^']+)'\)/.exec(reports).slice(1).join("");
  assert.ok(view.includes(falseText), `ReportsView must show jev.FALSE verbatim: ${falseText}`);
  assert.ok(view.includes(evidence), `ReportsView must show reports.EVIDENCE_RULE verbatim: ${evidence}`);
});

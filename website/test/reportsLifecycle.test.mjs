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

test("where a run goes is one prompt, and the card says the AI is answering it", async () => {
  // Three judgements of one run - "when should this reach you" (a three-way switch plus a
  // row-shaped condition), "move it up in the pipe if" (a sentence) and delivery's own copy of the
  // same three words - each with its own vocabulary, none of which could read prose. The owner
  // (2026-09-17): "make the UI clear that it's ai deciding it, so it's a prompt on the report for
  // routing". The old panels are replaced, not added to.
  assert.doesNotMatch(source, /WHEN SHOULD THIS REACH YOU\?/);
  assert.doesNotMatch(source, /MOVE IT UP IN THE PIPE IF/);
  assert.doesNotMatch(source, /TELL ME WHEN IT LOOKS WRONG/);
  const card = source.slice(source.indexOf("function RoutingCard"), source.indexOf("function ReportWizard"));
  assert.match(card, /ONE PROMPT THAT ROUTES EACH RUN/);
  // the sentence box shows what was typed, spaces included: a trimmed value is redrawn without its
  // trailing space, which is every space at the moment it is typed (the owner, 2026-09-17: "can't type
  // space here"). Trimming happens where the sentence is read (aiLines, reports.route_of), not here.
  const shownAs = card.slice(card.indexOf("const shownAs"), card.indexOf("const set = "));
  assert.match(shownAs, /r\.when \|\| "", r\]/);
  assert.doesNotMatch(shownAs, /\.trim\(\)/);
  assert.match(card, /how === "ai" && blank\(when\) &&/);
  assert.match(card, /<AutoAwesomeIcon/);                                  // the same grammar as the summary prompt
  assert.match(card, /<MenuItem value="ai"[^>]*>ask the AI<\/MenuItem>/);   // the control names who answers
  assert.match(card, /see the prompt/);
  assert.match(card, /ON THE LAST RUNS THIS WOULD HAVE/);
  // ...and WHO answers is said, not picked a second time. One judge setting lives under Triage & agents
  // for every report; blank there means the brain that writes the report, which is the picker above
  // the summary prompt. The card used to carry a second picker writing that very same field, and it
  // read as a per-report judge that the setting quietly overrode (the owner, 2026-09-17).
  assert.doesNotMatch(card, /ai_brain: e\.target\.value/);
  assert.match(card, /decides where each run goes/);
  assert.match(card, /window\.location\.hash = JUDGE_HASH/);
  assert.match(source, /const WHERE_RUNS_GO = "Settings › Triage & agents › Where runs go"/);
  assert.match(source, /if \(judge\?\.kind === "decision"\) return \[judge\.display/);
  assert.match(source, /return \["The brain that writes this report"/);
  // the hash it sets is one the page follows
  // (the canvas opens it as a Settings card - canvasLinks.js, pinned in test/canvasLinks.test.mjs)
  const links = await readFile(new URL("../src/canvasLinks.js", import.meta.url), "utf8");
  assert.match(links, /#settings=/);
  const hub = await readFile(new URL("../src/TaskHubPage.jsx", import.meta.url), "utf8");
  assert.match(hub, /window\.addEventListener\("hashchange", fromHash\)/);
});

test("a line the AI is not asked about is not the AI's to answer", () => {
  // `every run` means every run, and a report with no sentence anywhere asks no model at all -
  // the straight-report path the owner asked to keep free of AI (2026-09-17).
  assert.match(source, /const aiLines = \(c, lines\) => lines\.filter\(\(l\) => lineOf\(c, l\)\.how === "ai" && \(lineOf\(c, l\)\.when \|\| ""\)\.trim\(\)\)/);
  const card = source.slice(source.indexOf("function RoutingCard"), source.indexOf("function ReportWizard"));
  assert.match(card, /No AI is asked/);
});

test("the Timeline can only be silenced when the run has somewhere else to go", () => {
  // A report that reaches nobody at all is not a setting, it is a report that does nothing
  // (the owner, 2026-09-17: "they can send it out to whatever connector they choose so never on
  // timline/work makes sense").
  const card = source.slice(source.indexOf("function RoutingCard"), source.indexOf("function ReportWizard"));
  assert.match(card, /const canSilenceTimeline = !!cfg\.deliver\?\.to/);
  assert.match(card, /disabled=\{line === "timeline" && !canSilenceTimeline\}/);
});

test("see the prompt shows the prompt, word for word as the server builds it", () => {
  // A paraphrase of the real prompt would be worse than showing nothing. These strings are
  // reports.LINE_SAYS and the line reports.judge_prompt writes.
  assert.match(source, /timeline: "post it on the owner's timeline as news to read"/);
  // the work line is gone (the owner, 2026-09-28): whether a run is work is triage's call on every run
  assert.ok(!source.includes("put it on the owner's work rail"));
  assert.match(source, /\$\{l\.toUpperCase\(\)\}: yes\|no .* but only if: \$\{lineOf\(c, l\)\.when\.trim\(\)\}/);
});

test("the prompt shown is the prompt asked - no sentence anybody stopped asking for", () => {
  // The judge answers four booleans and nothing else, so that a model which cannot write prose can
  // be one of the things that answers. A card still promising a reason per line describes a prompt
  // that is no longer sent - and `see the prompt` exists precisely so it cannot.
  assert.doesNotMatch(source, /one short sentence saying why/);
  assert.doesNotMatch(source, /in one sentence each/);
  assert.match(source, /judgePrompt/);
});

test("every report is the card - the page draws it and never re-derives old rules", () => {
  // One rule set (the owner, 2026-09-27): the server writes every report down as its route card
  // (reports.from_old_rules), so the page has nothing left to convert and nothing to guess.
  for (const gone of ["seedRoute", "reachOf", "deliverSendOf", "assistantDefault", "isRouted", "answersInProse", "c.triage"]) {
    assert.ok(!source.includes(gone), `${gone} is the old rule set and must not come back`);
  }
  assert.match(source, /export const fullRoute = \(c\) =>/);
  assert.match(source, /const LINE_DEFAULT = \{ timeline: "always", send: "always", alert: "never" \}/);
  // ...a rule is arithmetic a model is not trusted with, and it is a line's fourth answer
  assert.match(source, /<MenuItem value="rule"[^>]*>when a rule trips<\/MenuItem>/);
  // ...and what a saved report does is said in the server's words
  assert.match(source, /source\.RouteWords/);
  // the interruption is named for being immediate, not for a device (2026-09-17)
  assert.doesNotMatch(source, /ping my phone/);
  assert.match(source, /alert: \["reach me right away"/);
  assert.match(source, /alert: "reach the owner right away, on whichever channel they chose"/);
});

test("delivery keeps its own line, and the card says where that line lives", () => {
  const panel = source.slice(source.indexOf("SEND IT SOMEWHERE (OPTIONAL)"), source.indexOf("<RoutingCard"));
  assert.match(panel, /one prompt that routes each run/);
  assert.doesNotMatch(panel, /cfg\.deliver\.when/);
  assert.match(panel, /cfg\.deliver\.gate/);
});


test("on an existing report the routing step's Continue saves before it advances", () => {
  // The routing card writes cfg, and cfg reached the server only from Save on step three. So
  // "put it on my Work rail", Continue, Run now left the server on the old rules - no report in
  // the owner's database ever carried a route block (2026-09-18: "it did not save? ... the
  // continue button?"). A new report has no title to save under yet, so it still only advances.
  const wizard = source.slice(source.indexOf("function ReportWizard"));
  const at = wizard.indexOf("<RoutingCard");
  const step = wizard.slice(at, wizard.indexOf("</StepContent>", at));
  // ...and only a save that worked moves on: a refused one stays on the step that says why
  assert.match(step, /onClick=\{async \(\) => \{ if \(cur && !\(await save\(\)\)\) return; setStep\(1\); \}\}/);
  assert.match(step, /\{cur \? "Save & continue" : "Continue"\}/);
  assert.match(step, /\{saveErr && /, "a refused save must say so on the step where the button is");
});

test("the Assistant with no rule of its own asks whether it matters before it shows under Reports", () => {
  // 2026-09-20: "only show up when the assistant has an idea that matters, not always" - an unsaved
  // Assistant report shows the sentence the server asks (reports.ASSISTANT_WHEN, reports.default_route)
  assert.match(source, /export const ASSISTANT_WHEN = "it has an idea that matters: /);
  assert.match(source, /c\?\.type === "assistant" && line === "timeline" \? \{ how: "ai", when: ASSISTANT_WHEN \}/);
});

test("triage reads every run that worked, against the brief the card gives it", () => {
  // the work line is gone (the owner, 2026-09-28) - its sentence is watch_for, the brief reports.work_brief reads
  assert.match(source, /export const ROUTE_LINES = \["timeline", "alert", "send"\]/);
  assert.match(source, /Make it a task when…/);
  assert.match(source, /value=\{cfg\.watch_for \|\| ""\} onChange=\{\(e\) => setCfg\(\{ \.\.\.cfg, watch_for: e\.target\.value \}\)\}/);
});

test("a report with no schedule wears a red border and says it only runs by hand", () => {
  // D2 (the owner, 2026-09-28): the row said "daily" and the page "blank = once a day" while it never ran on its own
  assert.ok(!source.includes('.join(" + ") || "daily"'));
  assert.match(source, /const unscheduled = !sched && !workflowOverview;/);
  assert.match(source, /No schedule — it only runs when you press Run now\./);
  assert.match(source, /Everything blank = it only runs when you press Run now\./);
});

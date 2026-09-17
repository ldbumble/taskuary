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

test("where a run goes is one prompt, and the card says the AI is answering it", () => {
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
  assert.match(card, /<AutoAwesomeIcon/);                                  // the same grammar as the summary prompt
  assert.match(card, /<MenuItem value="ai"[^>]*>ask the AI<\/MenuItem>/);   // the control names who answers
  assert.match(card, /see the prompt/);
  assert.match(card, /ON THE LAST RUNS THIS WOULD HAVE/);
});

test("a line the AI is not asked about is not the AI's to answer", () => {
  // `every run` means every run, and a report with no sentence anywhere asks no model at all -
  // the straight-report path the owner asked to keep free of AI (2026-09-17).
  assert.match(source, /export const asksAi = \(c\) => ROUTE_LINES\.some\(\(l\) => routeOf\(c, l\)\[0\] === "ai"\)/);
  const card = source.slice(source.indexOf("function RoutingCard"), source.indexOf("function ReportWizard"));
  assert.match(card, /No AI is asked/);
  // a line asking the AI with nothing to judge by is a question the model cannot answer
  assert.match(source, /how === "ai" && !when \? "always" : how/);
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
  assert.match(source, /work: "put it on the owner's work rail, as something they have to do"/);
  assert.match(source, /\$\{l\.toUpperCase\(\)\}: yes\|no .* but only if: \$\{routeOf\(c, l\)\[1\]\}/);
});

test("converting a report written before the card says the old rules out loud", () => {
  // Touching one line must not silently change the others behind your back, so seedRoute writes the
  // old rules down AS SENTENCES, on the card, before anything is saved - the owner can then argue
  // with them like any other. The work rail is the deliberate exception: it follows the new default
  // rather than the `triage` switch, which was off on every report that exists.
  assert.match(source, /export const seedRoute = \(c\) => \{/);
  assert.match(source, /work: \(c\?\.watch_for \|\| ""\)\.trim\(\) \? \{ how: "ai"/);   // the pipe sentence, else the default
  assert.match(source, /\{ how: "ai", when: c\.watch_for\.trim\(\) \}/);    // the pipe sentence becomes the work line's
  assert.match(source, /send: c\?\.deliver\?\.to \? from\(deliverSendOf\(c\), c\?\.deliver\) : \{ how: "always" \}/);
  assert.match(source, /const LINE_DEFAULT = \{ timeline: "always", send: "always", work: "always", alert: "never" \}/);
  // ...and the interruption is named for being immediate, not for a device: it goes wherever you
  // picked, as often email as WhatsApp (2026-09-17: "why does this say phone if it can go to email?")
  assert.doesNotMatch(source, /ping my phone/);
  assert.match(source, /alert: \["reach me right away"/);
  assert.match(source, /alert: "reach the owner right away, on whichever channel they chose"/);
});

test("the reading of an absent setting is the server's own, and prose is offered words", () => {
  // reports.reach_of does exactly this: a condition was the only way to ask for quiet, and an
  // assistant check was quiet already. If these two ever disagree the setup screen lies about
  // what the report will do.
  assert.match(source, /export const reachOf = \(c\) => \(\["always", "wrong", "rule"\]\.includes\(c\?\.reach\) \? c\.reach/);
  assert.match(source, /c\?\.alert\?\.when \? "rule" : c\?\.type === "assistant" \? "wrong" : "always"/);
  // "fewer rows than 5" on an AI summary compared five LINES, so a prose check is not offered it
  assert.match(source, /export const answersInProse = \(c\) => c\?\.type === "assistant" \|\| !!c\?\.ai_prompt/);
  const conditions = source.slice(source.indexOf("const CONDITIONS = ["), source.indexOf("];", source.indexOf("const CONDITIONS = [")));
  for (const row of ["fewer_than", "more_than"]) {
    const line = conditions.split("\n").find((l) => l.includes(row));
    assert.ok(line && !line.includes("prose:"), `${row} must not be offered to a check that answers in prose`);
  }
  assert.match(conditions, /v: "something_came_back", rows: "anything came back", prose: "it found something"/);
});

test("delivery keeps its own answer, and the card says where that answer now lives", () => {
  // Reach is about the OWNER; delivery sends the result somewhere else entirely. Tying them
  // together meant "only when something is wrong" silently stopped a monthly report going out to
  // the people waiting for it (the owner, 2026-09-17: "deliver is to push to somewhere not
  // timeline, that is something else"). Absent must keep meaning every run - reports.deliver_how.
  assert.match(source, /export const deliverSendOf = \(c\) => \(\["always", "wrong", "rule"\]\.includes\(c\?\.deliver\?\.send\) \? c\.deliver\.send : "always"\)/);
  const panel = source.slice(source.indexOf("SEND IT SOMEWHERE (OPTIONAL)"), source.indexOf("<RoutingCard"));
  assert.match(panel, /one prompt that routes each run/);       // the rule itself is a line on that card
  assert.doesNotMatch(panel, /cfg\.deliver\.when/);              // ...not a second row-shaped condition here
  assert.match(panel, /cfg\.deliver\.gate/);                     // the Review gate stays exactly where it was
});


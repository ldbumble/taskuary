// Every task-view control says what it does to the task and to the agent, and runs the shared operations road
// (PW-215..PW-221). The browser harness runs in demo mode, where mutating requests are denied, so behaviour is
// proven by the backend TestClient tests (tests/test_task_controls_operations.py) and these source assertions.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");
const tasks = src("TasksView.jsx");

test("each control carries the caption that names its effect on task versus agent", () => {
  for (const [label, title] of [
    ["Mark task done", "Closes the task and ends the live agent session with it."],
    ["Reopen task", "Reopens the task only. No agent starts until you choose one."],
    // one ending, and it writes the session up either way (2026-09-16)
    ["Save and end session", "The task stays open: Mark task done completes it and drafts the reply."],
    ["Save stopped run result", "Saves the stopped session's result and report. The task stays open."],
    // its label varies - "Write another" once a reply has already gone - but the caption does not
    // ONE reply button now, and it writes: the twin that drafted it was the thing the first one
    // was named for (2026-09-22), so the caption says what the press does
    ["{replyPrimary}", "Drafts the reply here, from this task's own context. Nothing is sent until you approve it."],
    ["Ask sender", "nothing is sent now."],
    ["Review changes", "Nothing is approved or committed here."],
  ]) {
    const at = tasks.indexOf(`>${label}</Button>`);
    assert.notEqual(at, -1, `${label} button`);
    const opening = tasks.lastIndexOf("<Button", at);
    assert.ok(tasks.slice(opening, at).includes(title), `${label}: caption "${title}"`);
  }
  // and the one dynamic label still says what it does in every state it can take
  assert.match(tasks, /const replyPrimary = pendingReview \? "Open the draft" : sentReview \? "Write another" : "Write reply";/);
});

test("the agent card's bar is the same bar as the task's and the reply's", () => {
  // It answered with a row of default-size buttons UNDER its body: a different size, a different
  // order, no rule between the move and the alternatives, and its one fact left where the other
  // two put theirs right (the owner, 2026-09-16: "this agent card is still weird and doesn't
  // match ... it should match the other ones"). One grammar: [ primary ] | [ named ] [ named ].
  assert.match(tasks, /const primaryBtn = \{ minHeight: 34/, "the filled move's shape is one value");
  const at = tasks.indexOf("const agentBarRow = (");
  assert.notEqual(at, -1, "the bar is one element the heading can carry");
  const bar = tasks.slice(at, tasks.indexOf("\n  );", at));
  assert.ok(bar.includes("sx={primaryBtn}"), "it opens with the same filled primary");
  assert.ok(bar.includes('<Divider orientation="vertical"'), "a rule divides this session from another one");
  assert.ok(bar.includes("sx={canContinue ? barBtn : primaryBtn}"), "the named moves take barBtn");
  // whichever state it is in, exactly one move is filled: continue it, file it, or run another
  assert.match(tasks, /const canContinue = !term\?\.alive && \(isGeneral \? generalStarted : !!detail\?\.resumable\);/);
  assert.match(tasks, /const canSave = !report && !wrapped;/);
});

test("the agent heading is one short line, live or not", () => {
  // A running session has always been a single strip - heading, chip, controls - and the stopped
  // card answered with a heading, a sentence under it, and a row of buttons under that (the owner,
  // 2026-09-17: "can we also keep the agent header simple and short like it is when coder is
  // active"). The bar rides IN the heading, so both extra lines go.
  const head = tasks.slice(tasks.indexOf('<WorkflowHeading number="2"'), tasks.indexOf('<WorkflowHeading number="3"'));
  assert.ok(head.includes("action={stage === \"agent\" && agentBar ? agentBarRow :"),
    "the expanded card's bar is the heading's action, not a row of its own");
  assert.ok(!head.includes("description="), "and nothing is said under the title");
  assert.ok(!/None of these completes the task/.test(tasks), "the sentence it used to carry is gone");
});

test("the agent card names the role and the brain, and offers no model", () => {
  // A role picks the document; a brain is the CLI that runs it. The model is the brain's -
  // brain_for(): "what it names is a brain - never a model, never an effort" - so the card must
  // not offer one. This is also a merge guard: b8c57823 resolved TasksView.jsx to its own side
  // and dropped this row entirely, and nothing failed, because nothing covered it.
  assert.match(tasks, /const runRole = assignedAgent\(t\?\.Assignee\) \|\| \(t\?\.Kind === "coding" \? "coder" : ""\);/);
  // `term.cli` is the literal string "taskuary" on every general session (general.info), so the
  // pill that exists to name the brain named the PRODUCT. The session's own provider leads now.
  assert.match(tasks, /const runBrain = term\?\.provider \|\| term\?\.cli \|\| term\?\.agent \|\| detail\?\.ranOn\?\.brain \|\| \(runRole && brains\[runRole\]\) \|\| "";/);
  assert.match(tasks, /const brainPill = runBrain && !\(isGeneral && term\?\.alive\) \? runBrain : "";/,
    "a live general session shows the brain in its workspace picker - the pill would be the same fact twice");
  assert.ok(tasks.includes("const { agents, models, kinds, brains, brainList, brainModels, generalBrains } = useAgents();"),
    "the roster's role->brain map has to reach the card");
  const at = tasks.indexOf("{runRole && <Box");
  assert.notEqual(at, -1, "the role pill must be rendered");
  const row = tasks.slice(at, at + 1400);
  assert.ok(row.includes(">role</Box>") && row.includes(">brain</Box>"), "both pills are labelled");
  assert.ok(row.includes("{brainPill &&"), "the brain pill renders brainPill, not runBrain");
  assert.ok(!/>model</.test(row), "and there is no model pill - the model is not the task's");
});

test("a live session still lets you act on the TASK", () => {
  // The task card is gated on !term?.alive, so while a session runs it is not on the page at all.
  // When its four controls lived behind the header's dots that did not matter; once the dots went
  // (2026-09-16) a live session had no way to complete, hand off, split or reject the task. The
  // header carries them for exactly that window - `sessionView`, which is the live session unless
  // the owner has stepped back to the task behind it (peek), where the card and its controls return.
  const at = tasks.indexOf('{sessionView && !["done", "dropped"].includes(t.Status) && (');
  assert.notEqual(at, -1, "the header must carry the task controls while a session fills the page");
  const bar = tasks.slice(at, at + 2200);
  for (const [what, hook] of [["Mark task done", 'finish("done")'], ["Not a task", "setConfirmNAT(true)"],
                              ["Hand it to a person", "setHandoff(true)"], ["Split or merge", "setReshape(true)"]]) {
    assert.ok(bar.includes(hook), `${what} must be reachable during a live session`);
  }
  assert.ok(tasks.includes("{!sessionView && ("), "and the full card is what you get when nothing is running, or when you stepped back to the task");
});

test("the rail says a task's state once, and puts its title first", () => {
  // The row used to carry LifecycleChip ("task · in progress") beside StateChip ("agent working"),
  // the same duplication the detail header had, with the title read last under both.
  const from = tasks.indexOf("shown.map((task) => {"), to = tasks.indexOf("</Empty> : shown.map", from + 1);
  const row = tasks.slice(from, to === -1 ? from + 4200 : to);
  assert.ok(row.includes("<StateChip task={task} />"), "the row keeps one state chip");
  assert.ok(!row.includes("<LifecycleChip"), "and must not say the same state a second way");
  assert.ok(row.indexOf("{task.Title}") < row.indexOf("data-tq-task-ref"), "the title comes before the ref");
});

test("complete, reopen, coding start and stop run the shared operations road, never a second path", () => {
  assert.match(tasks, /runOperation\(api, "task\.complete", selected\)/);
  assert.match(tasks, /runOperation\(api, "task\.reopen", selected\)/);
  assert.match(tasks, /runOperation\(api, "dispatch\.prepare", id, \{ kind: "coding"/);
  // there is no stop in this view any more, so there is no second path to guard - a session ends by
  // being written up, and that is the rule (the owner, 2026-09-16: "meaning no stop without saving").
  // Marking the task done still ends a live session, which is the way out of a wedged one.
  assert.doesNotMatch(tasks, /runOperation\(api, "agent\.stop"/);
  const start = tasks.slice(tasks.indexOf("const startCodingAgent"), tasks.indexOf("const startGeneralAgent"));
  assert.doesNotMatch(start, /Kind: "coding"/, "no Kind PATCH before a terminal");
  assert.doesNotMatch(start, /openTerm\(/, "the terminal comes from dispatch");
  assert.doesNotMatch(tasks, /patch\(\{ Status: "open" \}\)/, "reopen is an operation, not a raw PATCH");
});

test("saving a result never completes the task, drafts never send, a question waits on the task", () => {
  assert.match(tasks, /\/wrap`, \{ close: false \}/);
  assert.match(tasks, /\/reply`, \{ draft: generate \}/);
  assert.match(tasks, /\/clarify`, \{ body: text/);
  assert.doesNotMatch(tasks, /\/send`/);
});

test("the operations helper proposes then executes by version and surfaces a failed handler", () => {
  const ops = src("taskOps.js");
  assert.match(ops, /api\.post\("\/api\/operations", \{ kind, target, params \}\)/);
  assert.match(ops, /\/execute`, \{ version: op\.version \}/);
  // it still throws on a failed handler - and carries the halt's outcome, so a caller can ask
  // the question the handler stopped for (a repository still to choose) instead of printing it
  assert.match(ops, /data\?\.status === "error"\) \{/);
  assert.match(ops, /err\.outcome = data\.outcome \?\? null;/);
  assert.match(ops, /throw err;/);
});

test("interrupted work shows as interrupted and reopening starts nothing", () => {
  assert.match(tasks, /includes\("interrupted"\) && <Chip/);
  const from = tasks.indexOf("const reopen =");
  const reopen = tasks.slice(from, tasks.indexOf("};", from));
  assert.doesNotMatch(reopen, /dispatch/);
});

test("a task nobody sent offers no reply to write", () => {
  // the drafter answered the OWNER on a task he typed himself, in the box that sends (TQ-0674)
  const life = fs.readFileSync(path.join(process.cwd(), "src", "taskLifecycle.js"), "utf8");
  assert.match(life, /export const NO_ONE_BEHIND = \["", "own", "report", "assistant"\]/);
  assert.match(tasks, /const replyMessage = hasCorrespondent\(sourceMessage\) \? sourceMessage : null;/);
  assert.match(tasks, /api\.post\(`\/api\/messages\/\$\{replyMessage\.MessageId\}\/reply`/);
  assert.match(tasks, /Nobody sent this one, so there is nobody to answer/);
});

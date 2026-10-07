import { taskSource } from "./taskSource.mjs";
// Every task-view control says what it does to the task and to the agent, and runs the shared operations road
// (PW-215..PW-221). The browser harness runs in demo mode, where mutating requests are denied, so behaviour is
// proven by the backend TestClient tests (tests/test_task_controls_operations.py) and these source assertions.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");
const tasks = taskSource();

test("each control carries the caption that names its effect on task versus agent", () => {
  for (const [label, title] of [
    // ...and while the close runs it greys out and says "Marking done…" (2026-09-25)
    // ...and says only what it does HERE: the session part when one is live, the kept draft when one waits (T11)
    ['{finishing ? "Marking done…" : "Mark done"}', "title={markDoneHint}"],
    ["Reopen task", "Reopens the task only. No agent starts until you choose one."],
    // one ending, and it writes the session up either way (2026-09-16)
    ["Save and end session", "ends it, and drafts the reply to whoever asked. The task stays open until you complete it."],
    ["Save and end session", "Saves the stopped session's result and report. The task stays open."],
    // its label varies - "Write another" once a reply has already gone - but the caption does not
    // ONE reply button now, and it writes: the twin that drafted it was the thing the first one
    // was named for (2026-09-22), so the caption says what the press does
    // ...and while the AI writes it the label says "Drafting…" (2026-09-24)
    ['{openingReply ? "Drafting…" : replyPrimary}', "Drafts the reply here, from this task's own context. Nothing is sent until you approve it."],
    ["Ask sender", "nothing is sent now."],
    ["Review changes", "Nothing is approved or committed here."],
  ]) {
    // one name can sit on several buttons (every ending is "Save and end session", 2026-09-25): each
    // caption must be on one of them
    const ats = [];
    for (let at = tasks.indexOf(`>${label}</Button>`); at !== -1; at = tasks.indexOf(`>${label}</Button>`, at + 1)) ats.push(at);
    assert.ok(ats.length, `${label} button`);
    assert.ok(ats.some((at) => tasks.slice(tasks.lastIndexOf("<Button", at), at).includes(title)), `${label}: caption "${title}"`);
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
  assert.ok(bar.includes("sx={barContinue ? barBtn : primaryBtn}"), "the named moves take barBtn");
  // a general agent's composer sits under this bar and continues the same conversation: no second door (2026-09-29)
  assert.match(tasks, /const barContinue = canContinue && !isGeneral;/);
  assert.ok(bar.includes("{barContinue && <Button"), "the bar's Continue session is the coding agent's only");
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
  assert.ok(head.includes("action={inRow ? null : stage === \"agent\" && agentBar ? agentBarRow :"),
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
  // the condition has a name now (it also decides whether the header strip may wrap on a phone)
  assert.match(tasks, /const headControls = sessionView && !inRow && notDone;/);
  assert.match(tasks, /const notDone = !!t && !\["done", "dropped"\]\.includes\(t\.Status\);/);
  const at = tasks.indexOf("{headControls && (");
  assert.notEqual(at, -1, "the header must carry the task controls while a session fills the page");
  const bar = tasks.slice(at, at + 2200);
  // Mark done goes through askFinish, which asks first while an agent session is live (2026-09-25)
  assert.match(tasks, /const askFinish = \(\) => \(liveSession \? setConfirmDone\(true\) : finish\("done"\)\)/);
  for (const [what, hook] of [["Mark task done", "onClick={askFinish}"], ["Not a task", "setConfirmNAT(true)"],
                              ["Hand it to a person", "setHandoff(true)"], ["Split or merge", "setReshape(true)"]]) {
    assert.ok(bar.includes(hook), `${what} must be reachable during a live session`);
  }
  assert.ok(tasks.includes("{!sessionView && ("), "and the full card is what you get when nothing is running, or when you stepped back to the task");
  // on the canvas the same four ride in the action row instead, registered whatever the session is doing
  for (const id of ["done", "nat", "hand", "reshape"]) assert.ok(tasks.includes(`{ id: "${id}", group: "more"`), `the row carries ${id}`);
});

test("the rail says a task's state once, and puts its title first", () => {
  // The row used to carry LifecycleChip ("task · in progress") beside StateChip ("agent working"),
  // the same duplication the detail header had, with the title read last under both.
  const from = tasks.indexOf("shown.map((task) => {"), to = tasks.indexOf("</Empty> : shown.map", from + 1);
  const row = tasks.slice(from, to === -1 ? from + 6000 : to);     // the row's code, with room to grow (it sat at 3,996 of 4,200)
  assert.ok(row.includes("<StateChip task={task} />"), "the row keeps one state chip");
  assert.ok(!row.includes("<LifecycleChip"), "and must not say the same state a second way");
  assert.ok(row.indexOf("{task.Title}") < row.indexOf("data-tq-task-ref"), "the title comes before the ref");
});

test("complete, reopen, coding start and stop run the shared operations road, never a second path", () => {
  assert.match(tasks, /runOperation\(api, "task\.complete", selected[,)]/);   // a close with a note rides the same road
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
  // the box opens at once and the AI's draft is written behind it (replyDraft.js, 2026-10-01) - neither sends
  assert.match(tasks, /generate \? draftReply\(api, replyMessage\.MessageId\) : api\.post\(`[^`]*\/reply`, \{ draft: false \}\)/);
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
  // the row's state chip says "agent stopped" once - no second chip beside it (T1, 2026-09-25)
  assert.doesNotMatch(tasks, /includes\("interrupted"\) && <Chip size="small" label="agent stopped"/);
  assert.match(tasks, /<StateChip task=\{task\} \/>/);
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

test("a draft that cannot be sent says why on the card, not in a tooltip", () => {
  // outbound.send_block writes one sentence for exactly this (PW-044) and every other surface
  // shows it; the task page kept it in the hover of the button that replaced Send
  const decision = fs.readFileSync(path.join(process.cwd(), "src", "ReviewDecision.jsx"), "utf8");
  assert.match(decision, /r\.CanSend === false && \(/);
  assert.match(decision, /No reply can be sent from here — \{r\.SendBlock/);
  assert.match(decision, /The draft stays for you to use/);
});

test("Mark done on a live session ends it the way Save and end session does", () => {
  // the owner, 2026-09-29: the confirm killed the pty with no write-up, and the terminal stayed on screen for the whole
  // close - Save and end session swaps it for the write-up's progress line at once, files the result, then this closes
  assert.ok(tasks.includes("onConfirm={stopAndFinish}"), "the confirm takes the write-up road");
  const at = tasks.indexOf("const stopAndFinish = async");
  const body = tasks.slice(at, tasks.indexOf("\n  };", at));
  assert.ok(body.indexOf('setWrapping("done")') < body.indexOf("/wrap"), "the terminal gives way before the request");
  assert.ok(body.includes("no_reply: true"), "the close dismisses drafts, so none is written");
  assert.ok(body.indexOf("/wrap") < body.indexOf('finish("done")'), "the result is filed before the task closes");
});

// RUN ANOTHER AGENT (the owner, 2026-10-05: "don't see run another agent under more? it should be not in more"): it was behind
// More, only on a coding task, only after its session ended - so a general task's live session could never be handed to the
// coding agent. It stands on the bar for any task an agent has worked, opens the agent step, and pauses a live session first.
test("run another agent is on the bar, live sessions and general tasks included", () => {
  assert.match(tasks, /const runAnother = \{ id: "run-another", group: "agent"/);
  const live = tasks.slice(tasks.indexOf("...(liveSession ? ["), tasks.indexOf("] : continueHere ?"));
  assert.match(live, /runAnother/, "a live session offers it beside Save and end session");
  assert.doesNotMatch(tasks, /id: "run-another", group: "more"/);
});

test("its agent step opens on a general task and beside a live session", () => {
  assert.match(tasks, /\{\(restartOpen \|\| \(!term\?\.alive && !liveRun && !isGeneral && !report && !detail\?\.transcript\)\)/);
});

test("on the canvas it is a card under the conversation in Continue's place, one at a time, closed when the agent starts", () => {
  assert.match(tasks, /nextRunSlot && createPortal\(/);
  assert.match(tasks, /&& !\(canvas && restartOpen\) && nextRunForm\}/, "not drawn twice");
  assert.match(tasks, /const setContinueAt = \(a\) => \{\s+if \(a\) setRestartOpen\(false\);/);
  assert.match(tasks, /window\.dispatchEvent\(new CustomEvent\("tq-next-run"\)\)/);
  const start = tasks.slice(tasks.indexOf("const startCodingAgent"), tasks.indexOf("const startGeneralAgent"));
  assert.match(start, /setRestartOpen\(false\)/);
});

test("starting the new one pauses a live session first - its handover kept, no report, no reply draft", () => {
  const start = tasks.slice(tasks.indexOf("const startCodingAgent"), tasks.indexOf("const startGeneralAgent"));
  assert.ok(start.indexOf("/pause") > 0 && start.indexOf("/pause") < start.indexOf('"dispatch.prepare"'));
});

test("an unstarted general task's Send to agent is the row's lead, not a button inside the card", () => {
  assert.match(tasks, /const sendGeneral = isGeneral && !generalStarted && notDone && !liveSession;/);
  assert.match(tasks, /sendGeneral \? \[\{ id: "send-general", group: "agent", lead: !pendingReview/);
  assert.match(tasks, /\{!inRow && <Button size="small" variant="contained" disableElevation disabled=\{!!startingAgent\}\s+startIcon=\{startingAgent === "general"/);
});

test("a live session's Mark done asks for a place on the bar", () => {
  assert.match(tasks, /promote: !liveSession && !pendingReview, beside: liveSession, onCard: !!pendingReview && !liveSession \}/);   // ...and a waiting draft's send is the move (2026-10-06)
});

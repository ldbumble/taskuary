import test from "node:test";
import assert from "node:assert/strict";
import { NEXT_STEP, whyFailed } from "../src/stepWhy.js";
import { stepsOf } from "../src/agentSteps.js";
test("a failed step opens on the line that says what went wrong", () => {
  assert.equal(whyFailed("cd C:/work\n$ python pull.py\nTraceback (most recent call last):\n  File \"pull.py\", line 3\nFileNotFoundError: no such file: lk.sql"),
    "Why: FileNotFoundError: no such file: lk.sql");
  assert.equal(whyFailed(""), "It stopped without saying why.");
});

// A TOOL'S REFUSAL IS TWO LINES (the UI judge, 2026-11-18: "use_repo picks it (find_repos lists them)" was the owner's Why line): what happened,
// for him; the agent's next step, tool names and all, on the line the Why line leaves out
test("a refusal's next step is the agent's, never the owner's Why line", () => {
  assert.equal(whyFailed(`there is no report 99\n${NEXT_STEP}\`report\` is the N of its #report=N - search_tasks gives it on a report's hit`, true), "Why: there is no report 99");
  assert.equal(whyFailed(`nothing was pushed - origin refused it\n${NEXT_STEP}pull, then call propose_land again`, true), "Why: nothing was pushed - origin refused it");
  assert.equal(whyFailed(`${NEXT_STEP}call it again`, true), "It stopped without saying why.");
});

// ...AND ONLY A TASKUARY TOOL'S (the robustness judge, 2026-11-18): any other program's output is its own, and a CLI's line that starts with the
// same words - its only line, even - is what he reads, never "It stopped without saying why."
test("a command's own line that starts like a next step is kept, and only Taskuary's tools are read as refusals", () => {
  assert.equal(whyFailed("Next: run the migrations first"), "Why: Next: run the migrations first");
  const failedStep = (name) => stepsOf([{ type: "tool_call", name, detail: { tool_call_id: "c1", args: {} } },
    { type: "tool_result", name, detail: { tool_call_id: "c1", result: `the step went wrong\n${NEXT_STEP}call it again`, is_error: true } }])[0];
  const own = ["mcp__taskuary__share", "taskuary__propose_land", "read_message", "share", "propose_land", "remind"].map((n) => failedStep(n));
  for (const st of own) assert.equal(whyFailed(st.detail, st.own), "Why: → the step went wrong", st.raw);
  for (const n of ["Bash", "mcp__github__create_pr", "run_command"]) { const st = failedStep(n); assert.equal(whyFailed(st.detail, st.own), `Why: ${NEXT_STEP}call it again`, n); }
});

// ...AND THE SAME RULE ON EVERY SURFACE (the UI judge, 2026-11-18): the general road files a failed call's words as their own "⚠" note, and the
// Wall's pane and the task chat read "⚠ there is no report 9 ⏎ Next: `report` is the N of its #report=N - ..." - the agent's step, to him
test("a failed call's own note on the general road says what happened, never the agent's next step", async () => {
  const { eventsOf, turnParts } = await import("../src/chatStream.js");
  const kept = [{ k: "tool", name: "mcp__taskuary__share", text: "" },
    { k: "error", name: "mcp__taskuary__share", text: `there is no report 9 ⏎ ${NEXT_STEP}\`report\` is the N of its #report=N - search_tasks gives it on a report's hit` },
    { k: "tool", name: "read_message", text: "m999" }, { k: "error", name: "read_message", text: `Taskuary has no saved message m999\n${NEXT_STEP}search_messages finds a message and its id` },
    { k: "error", name: "Bash", text: `make: *** [all] Error 2 ⏎ ${NEXT_STEP}run the migrations first` },
    { k: "error", text: "the agent stopped in the middle of its turn" }];
  const steps = turnParts(eventsOf(kept, false)).flatMap((p) => p.steps || []);
  // ...a failure its call names is that call's own step, failed, its words behind it (design round 4, 2026-11-19) - read without the next step
  const own = steps.filter((s) => s.kind !== "error");
  assert.deepEqual(own.map((s) => s.status), ["error", "error"]);
  for (const s of own) assert.doesNotMatch(whyFailed(s.detail, s.own), new RegExp(NEXT_STEP.trim()));
  assert.match(whyFailed(own[1].detail, own[1].own), /no saved message m999/);
  const notes = steps.filter((s) => s.kind === "error").map((s) => s.summary);
  assert.deepEqual(notes, [`⚠ make: *** [all] Error 2 ⏎ ${NEXT_STEP}run the migrations first`, "⚠ the agent stopped in the middle of its turn"]);
});

// ...AND ONLY THE LAST LINE, WHICH THE TOOL ALONE WRITES (the robustness judge, 2026-11-18): a connected system's own "Next: ..." line is its
// words, quoted by the tool (agenttools.steps_of) - he reads it, never "Why: upstream said:"
test("a connected system's own next-step line is the owner's to read", () => {
  assert.equal(whyFailed("upstream said:\n> Next: page token expired, re-login required", true), "Why: > Next: page token expired, re-login required");
  assert.equal(whyFailed(`the export\n${NEXT_STEP}retry failed upstream\nnothing was sent\n${NEXT_STEP}call it again`, true), `Why: ${NEXT_STEP}retry failed upstream`);
});

// ...AND ONE DEFINITION OF THE MARKS ON BOTH SIDES (the robustness judge, 2026-11-18): the page read " ⏎ " as a break and the tool did not
// neutralise it, so a value or a connected system's words made a line the owner's side dropped. Both read taskuary/nextstep.json; the tool
// shows any other text's break as `shown_break`, which the page reads as words
test("the page reads the tool's own marks, and a shown break is words", async () => {
  const { forOwner } = await import("../src/stepWhy.js");
  const marks = (await import("../../taskuary/nextstep.json", { with: { type: "json" } })).default;
  assert.equal(NEXT_STEP, marks.next_step);
  assert.equal(forOwner(`what happened${marks.line_mark}${marks.next_step}call it again`, true), "what happened");
  assert.equal(forOwner(`upstream refused: token expired${marks.shown_break}${marks.next_step}re-login at the vendor portal`, true),
    `upstream refused: token expired${marks.shown_break}${marks.next_step}re-login at the vendor portal`);
});

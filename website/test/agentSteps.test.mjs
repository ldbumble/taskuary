// ONE STEP MODEL, WHATEVER THE BACKEND (the owner, 2026-10-21: "make the output on the general agent canvas more readable, not some
// greps and gets"). The traces are the ones tests/test_agent_steps_backends.py makes from each backend's recorded stream - one invented
// research turn - so what is asserted here is what that backend's real parser hands the canvas.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { describeCall, isWork, stepsOf } from "../src/agentSteps.js";

const DIR = new URL("../../tests/fixtures/agent_steps/", import.meta.url);
const trace = (b) => JSON.parse(fs.readFileSync(new URL(`${b}.trace.json`, DIR), "utf8"));
const ANSWER = "The budget review is waiting on Gail Moreno's sign-off: TQ-1142 holds the thread, and the status board reads approvedTotal "
  + "before the review closes, so it shows last month's figure until then.";
const SAY = "I'll find the budget review thread first, then check the status board code.";
const CLIS = ["claude", "codex", "opencode", "gemini_acp"];
const APIS = ["openai_responses", "anthropic_api"];
const WORK = [
  "Searched your mail for 'budget review' (3 results)",
  "Opened TQ-1142",
  "Read 2 files in Budget/",
  "Searched files for 'approvedTotal'",
  "Searched the web for 'northwind budget review policy'",
  "Read a page on docs.northwind.example",
];
const work = (b) => stepsOf(trace(b), { answer: ANSWER, keepStart: false }).filter(isWork);
// what the canvas shows with every row closed: the summaries, and the agent's own words
const mainView = (steps) => steps.map((s) => s.summary).join("\n");

test("every CLI's recorded turn renders to the same plain steps", () => {
  for (const b of CLIS) assert.deepEqual(work(b).map((s) => s.summary), WORK, b);
  for (const b of CLIS) assert.ok(work(b).every((s) => s.status === "done"), b);
});

test("an API connector's own web searches read exactly like a CLI's", () => {
  for (const b of APIS) assert.deepEqual(work(b).map((s) => s.summary), WORK.slice(4), b);
});

test("the agent's prose comes through as its own words, once, and the answer is not repeated above itself", () => {
  const claude = stepsOf(trace("claude"), { answer: ANSWER, keepStart: false });
  assert.deepEqual(claude.filter((s) => s.kind === "said").map((s) => s.summary), [SAY]);
  assert.equal(claude[0].kind, "said");                                   // in the order it happened: it said, then it worked
  for (const b of CLIS) assert.ok(!mainView(stepsOf(trace(b), { answer: ANSWER })).includes("last month's figure"), b);
});

test("no raw script, token header, env name, JSON dump or key list reaches the main view", () => {
  for (const b of [...CLIS, ...APIS]) {
    const shown = mainView(stepsOf(trace(b), { answer: ANSWER }));
    for (const raw of ["X-Taskuary-Token", "TASKUARY_TOKEN", "TASKUARY_URL", "python -X", "json.load", "curl", "bash -lc", "sed -n",
      "'task', 'comments'", "{\"data\"", "C:\\Users", "/home/alex", "session started", "→ ", "claude-opus-5", "$"]) {
      assert.ok(!shown.includes(raw), `${b} shows ${raw}:\n${shown}`);
    }
  }
});

test("...and the raw call stays one disclosure away, for debugging", () => {
  const [mail] = work("claude");
  assert.match(mail.detail, /^\$ cd \/c\/Users\/alex\/\.taskuary\/scratch && H=/);
  assert.match(mail.detail, /→ \{"data"/);
});

test("no step is drawn twice: a structured backend's echo lines are not a second copy", () => {
  for (const b of CLIS) {
    const steps = stepsOf(trace(b), { answer: ANSWER, keepStart: false });
    const seen = steps.map((s) => s.summary);
    assert.equal(new Set(seen).size, seen.length, `${b}: ${seen.join(" | ")}`);
    assert.equal(steps.length, WORK.length + (b === "gemini_acp" ? 0 : 1), `${b}: ${seen.join(" | ")}`);
  }
  // the echo lines are really there in the claude trace - they used to land in "Agent progress"
  assert.ok(trace("claude").some((e) => e.type === "live" && String(e.detail).startsWith("→ Bash:")));
});

test("a CLI that streams only lines is read off its lines, as one block of prose", () => {
  const steps = stepsOf([{ type: "live", name: "muse", detail: "Looking at the thread." }, { type: "live", name: "muse", detail: "It needs a sign-off." }]);
  assert.deepEqual(steps.map((s) => [s.kind, s.summary]), [["said", "Looking at the thread.\nIt needs a sign-off."]]);
});

test("summaries come from the call's own arguments", () => {
  assert.equal(describeCall("Bash", { command: "git status" }).summary, "Ran git status");
  assert.equal(describeCall("Bash", { command: "ls -la", description: "List the scratch folder" }).summary, "Listed the files here");
  assert.equal(describeCall("Bash", { command: "./build.sh --fast", description: "Build the report" }).summary, "Build the report");
  assert.equal(describeCall("Glob", { pattern: "**/*.js" }).summary, "Looked for files matching '**/*.js'");
  assert.equal(describeCall("Edit", { file_path: "/srv/northwind/ledger/app.py" }).summary, "Edited app.py");
  assert.equal(describeCall("file change", { changes: [{ path: "a.py" }, { path: "b.py" }] }).summary, "Changed 2 files");
  assert.equal(describeCall("TodoWrite", { todos: [{}, {}, {}] }).summary, "Updated its plan (3 steps)");
  assert.equal(describeCall("mcp__github__search_issues", { query: "budget" }).summary, "Used search issues (github) on 'budget'");
  assert.equal(describeCall("shell", { command: 'curl -s -X POST "$TASKUARY_URL/api/tools/run" -d \'{"type": "mssql"}\'' }).summary,
    "Looked up data in mssql");
  assert.equal(describeCall("sync_messages", { new: 2 }).summary, "Checked for new mail (2 new)");
});

test("a failed or still-running call says so on its row", () => {
  const steps = stepsOf([
    { type: "tool_call", name: "Read", detail: { tool_call_id: "a", args: { file_path: "/x/notes.md" } } },
    { type: "tool_result", name: "a", detail: { result: "no such file", is_error: true } },
    { type: "tool_call", name: "WebSearch", detail: { tool_call_id: "b", args: { query: "northwind" } } },
  ]);
  assert.deepEqual(steps.map((s) => s.status), ["error", "running"]);
});

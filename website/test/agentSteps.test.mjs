// ONE STEP MODEL, WHATEVER THE BACKEND (the owner, 2026-10-21: "make the output on the general agent canvas more readable, not some
// greps and gets"). The traces are the ones tests/test_agent_steps_backends.py makes from each backend's recorded stream - one invented
// research turn - so what is asserted here is what that backend's real parser hands the canvas.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { describeCall, isWork, stepsOf } from "../src/agentSteps.js";

test("a heredoc written into a file reads as that file written, never 'Read <<EOF, and N more' (stress test 2026-11-02)", () => {
  const said = (command) => describeCall("Bash", { command }).summary;
  assert.equal(said(`cat > /work/outputs/TQ-0001/desk.svg <<'EOF'\n<svg width="10" a='b'></svg>\nEOF`), "Wrote desk.svg");
  assert.equal(said("mkdir -p out && cat <<EOF > out/notes.md\nhi\nEOF"), "Wrote notes.md");
  assert.equal(said("cat notes.md"), "Read notes.md");
  assert.doesNotMatch(said("cat notes.md > /dev/null"), /^Wrote/);
});

test("a folder the shell fills in ($d) is never shown as its name: the agent's own words for the step are (stress test 2026-11-03)", () => {
  const command = "$d=Join-Path $env:USERPROFILE 'Downloads'; $d; Get-ChildItem $d -Filter 'notes*' | Select Name; Get-ChildItem . -Recurse -Filter 'notes*'";
  assert.equal(describeCall("PowerShell", { command, description: "Locate the zip in Downloads" }).summary, "Locate the zip in Downloads");
  assert.equal(describeCall("PowerShell", { command }).summary, "Looked for files matching 'notes*', and 1 more");
  assert.equal(describeCall("PowerShell", { command: "Get-ChildItem $d | Select Name" }).summary, "Listed the files");
  assert.equal(describeCall("Bash", { command: 'cat "$f"' }).summary, "Read a file");
  assert.equal(describeCall("Bash", { command: "type %TEMP%\\notes.txt" }).summary, "Read a file");
  assert.equal(describeCall("Bash", { command: "ls ~/Downloads" }).summary, "Listed the files in Downloads");
  // ...and a pattern it looked for is not a folder it listed
  const find = 'Get-ChildItem -Recurse -Filter "notes-missing*" -Path "$env:USERPROFILE\\Downloads" -ErrorAction SilentlyContinue | Select FullName';
  assert.equal(describeCall("PowerShell", { command: find, description: "Search for the named zip elsewhere" }).summary, "Search for the named zip elsewhere");
  assert.equal(describeCall("PowerShell", { command: find }).summary, "Looked for files matching 'notes-missing*'");
  assert.equal(describeCall("Bash", { command: "ls ~/Downloads/*.zip" }).summary, "Looked for files matching '*.zip'");
  // ...nor a file it looked at a folder it listed
  assert.equal(describeCall("Bash", { command: "ls -la ~/Downloads/notes.zip 2>&1" }).summary, "Looked at notes.zip");
  assert.equal(describeCall("Bash", { command: "ls -la ~/Downloads/notes.zip", description: "Locate the zip in Downloads" }).summary, "Locate the zip in Downloads");
});

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

// A RETRY THAT WORKED IS NO FAILURE (the stress test, 2026-11-02): the agent's own retried steps wore red "failed" though it recovered
test("a failed step the agent retried with success reads as recovered; one never retried stays failed", () => {
  const call = (id, name, args) => ({ type: "tool_call", name, detail: { tool_call_id: id, args } });
  const res = (id, bad) => ({ type: "tool_result", name: id, detail: { result: bad ? "exit 1" : "ok", is_error: bad } });
  const steps = stepsOf([
    call("a", "Bash", { command: "npm test" }), res("a", true),
    call("b", "Read", { file_path: "/x/notes.md" }), res("b", false),
    call("c", "Bash", { command: "npm test" }), res("c", false),
    call("d", "Bash", { command: "git push" }), res("d", true),
  ]);
  assert.deepEqual(steps.map((s) => [s.summary, s.status]), [["Ran npm test", "recovered"], ["Read notes.md", "done"], ["Ran npm test", "done"], ["Ran git push", "error"]]);
  // ...and back to back, folded into one row: the row is the retry that worked
  const twice = stepsOf([call("a", "Bash", { command: "npm test" }), res("a", true), call("b", "Bash", { command: "npm test" }), res("b", false)]);
  assert.deepEqual(twice.map((s) => s.status), ["recovered"]);
  // ...but the last try failing is a failure, whatever came before
  const last = stepsOf([call("a", "Bash", { command: "npm test" }), res("a", false), call("b", "Bash", { command: "npm test" }), res("b", true)]);
  assert.deepEqual(last.map((s) => s.status), ["error"]);
});

// A HELD STEP WAITS, IT DID NOT FAIL (the desktop stress test, 2026-11-03): a delete Taskuary held for the owner wore red "failed"
test("a step Taskuary held for the owner's yes reads as held, never failed", () => {
  const call = (id, command, description) => ({ type: "tool_call", name: id, detail: { tool_call_id: id, args: { command, description } } });
  const res = (id, result) => ({ type: "tool_result", name: id, detail: { result, is_error: true } });
  const steps = stepsOf([
    { ...call("a", 'Remove-Item "C:/Users/alex/Downloads/notes" -Recurse', "Delete the extracted folder"), name: "PowerShell" },
    res("a", "PreToolUse:PowerShell hook error: Taskuary held this for the owner: delete notes in Downloads (it can't be undone). It is on the task"),
    { ...call("b", "npm test"), name: "Bash" }, res("b", "exit 1"),
  ]);
  assert.deepEqual(steps.map((s) => s.status), ["held", "error"]);
});

// A LOOK THAT FOUND NOTHING ANSWERED (the desktop stress test, 2026-11-03): `ls notes*` with no match is no failure
test("a look whose non-zero exit is its answer reads 'found none'; a look that broke, or any other step, still fails", () => {
  const call = (name, command, description) => ({ type: "tool_call", name, detail: { tool_call_id: "a", args: { command, description } } });
  const res = (result) => ({ type: "tool_result", name: "a", detail: { result, is_error: true } });
  const st = (name, command, result, description) => stepsOf([call(name, command, description), res(result)])[0].status;
  assert.equal(st("Bash", "ls notes*", "Exit code 2\nls: cannot access 'notes*': No such file or directory"), "none");
  assert.equal(st("Bash", "cd ~/Downloads && ls notes*", "Exit code 2\nls: cannot access 'notes*': No such file or directory", "Look for the notes"), "none");
  assert.equal(st("Bash", "grep -r invoice-4471 docs", "Exit code 1"), "none");
  assert.equal(st("PowerShell", "Get-ChildItem C:/Users/alex/Downloads/notes", "Get-ChildItem : Cannot find path 'C:\\Users\\alex\\Downloads\\notes' because it does not exist."), "none");
  assert.equal(st("Bash", "ls --frobnicate notes*", "Exit code 2\nls: unrecognized option '--frobnicate'\nTry 'ls --help' for more information."), "error");
  assert.equal(st("Bash", "npm test", "Exit code 1"), "error");
});

test("a turn whose answer carries its reply draft is not shown twice - the stream had the draft taken out, the filed answer keeps it", () => {
  const report = "My recommendation is to send Erin alone.\n\n**Worth going.** The tax changes land in January.";
  const after = "If you'd rather send both of them, tell me and I'll rewrite the reply.";
  const draft = "Hi Erin,\n\nYes, I think we should go.\n\nThanks,\nAlex Doyle";
  const streamed = [{ type: "progress", name: "text", detail: `${report}\n\n\n\n${after}` }];
  assert.deepEqual(stepsOf(streamed, { answer: `${report}\n\n${draft}\n\n${after}`, keepStart: false }).filter((s) => s.kind === "said"), []);
  // ...while words the answer does not say stay the agent's own
  assert.equal(stepsOf(streamed, { answer: `${report}\n\n${draft}`, keepStart: false }).filter((s) => s.kind === "said").length, 1);
});

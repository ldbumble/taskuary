// SHOW THE WORK AS IT HAPPENS (the owner, 2026-11-05: "it has to show what it's working on a little more than this like pulling from url's
// etc.. look how other chat libraries show intermediately the tool calls etc.") and THE TURN'S CLOCK ("it should show right when it starts the
// counter on top, then it stops when response is generated")
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { describeCall, pageOf, present, stepLabel, stepsOf } from "../src/agentSteps.js";
import { clockText, turnBegan, turnStamp } from "../src/agentWork.js";

const read = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const doing = (name, args) => stepLabel({ ...describeCall(name, args), status: "running" });
const did = (name, args) => stepLabel({ ...describeCall(name, args), status: "done" });

test("a running step says what it is doing, from the call's own arguments", () => {
  assert.equal(doing("WebSearch", { query: "northwind budget policy" }), 'Searching the web for "northwind budget policy"');
  assert.equal(doing("WebFetch", { url: "https://docs.northwind.example/budget/review" }), "Reading docs.northwind.example/budget/review");
  assert.equal(doing("Bash", { command: "agent-browser open https://portal.vendor.example/login" }), "Opening portal.vendor.example in the browser");
  assert.equal(doing("Read", { file_path: "/srv/northwind/notes.md" }), "Reading notes.md");
  assert.equal(doing("Write", { file_path: "/work/outputs/report.csv" }), "Writing report.csv");
  assert.equal(doing("Bash", { command: "npm test -- --watch" }), "Running npm test");
  assert.equal(doing("mcp__taskuary__my_task", {}), "Looking at the task's emails");
  assert.equal(doing("mcp__taskuary__search_messages", { words: "invoice" }), 'Searching your mail for "invoice"');
  // ...and once done, the same step in the past
  assert.equal(did("WebFetch", { url: "https://docs.northwind.example/budget/review" }), "Read docs.northwind.example/budget/review");
  assert.equal(did("mcp__taskuary__my_task", {}), "Looked at the task's emails");
  assert.equal(present("Edited app.py"), "Editing app.py");
  assert.equal(present("Build the report"), "Build the report", "the agent's own words stay its own");
});

test("an address is shown as host and path - never its query string, a sign-in, or a key in its path", () => {
  assert.equal(pageOf("https://user:pw@www.docs.northwind.example/budget/review?token=abc123&x=1#top"), "docs.northwind.example/budget/review");
  assert.equal(pageOf("https://api.vendor.example/v1/files/ab12cd34ef56gh78ij90kl12mn34/raw"), "api.vendor.example/v1/files/…/raw");
  for (const s of [doing("WebFetch", { url: "https://vendor.example/a?key=SECRET" }), doing("Bash", { command: "curl -s 'https://vendor.example/a?key=SECRET'" })])
    assert.ok(!/SECRET|key=|pw@/.test(s), s);
});

test("a run of calls still under way says its newest one", () => {
  const call = (id, file_path) => ({ type: "tool_call", name: "Read", detail: { tool_call_id: id, args: { file_path } } });
  const [s] = stepsOf([call("a", "/n/Budget/StatusBoard.js"), { type: "tool_result", name: "a", detail: { result: "ok" } }, call("b", "/n/Budget/BudgetTable.js")], { keepStart: false });
  assert.equal(s.status, "running");
  assert.equal(stepLabel(s), "Reading BudgetTable.js");
  assert.equal(s.summary, "Read 2 files in Budget/");
});

test("the turn's stamp: working m:ss while it runs, ran once it answered, nothing it cannot know", () => {
  const t0 = Date.parse("2026-11-05T15:00:00");
  assert.equal(turnStamp({ running: true, start: t0, now: t0 + 42_000 }), "working 0:42");
  assert.equal(turnStamp({ running: true, start: t0, now: t0 + 72_400 }), "working 1:12");
  assert.equal(turnStamp({ running: false, start: t0, end: t0 + 72_000 }), "ran 1m 12s");
  assert.equal(turnStamp({ running: true, start: null, now: t0 }), "", "no start, no counter");
  assert.equal(turnStamp({ running: false, start: t0, end: t0 + 7 * 3600_000 }), "", "a chat come back to hours later is no turn's run");
  assert.equal(clockText(3_725_000), "1:02:05");
});

test("a running turn shows its steps open, the newest six, and ONE clock - its working line's, never a second on its head", () => {
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /const LIVE_SHOWN = 6;/);
  assert.match(ws, /data-tq-live-steps=""/);
  assert.match(ws, /plural\(cut, "earlier step"\)/);
  assert.match(ws, /const stepsWord = \(parts\) => \{ const n = workCount\(parts\); return n \? plural\(n, "step"\) : "Along the way"; \};/, "an ended turn folds to N steps");
  assert.doesNotMatch(ws, /<Ticking|data-tq-working-for/, "the head's \"working 0:03\" is gone (the owner, 2026-11-06)");
  assert.match(ws, /<span>Working on this…<\/span>\s*<em>\{since \? elapsedText\(now - since\)/);
  assert.match(ws, /since: session\.turn_started \* 1000/, "the turn's own start, from the server");
  assert.match(read("AgentStepRows.jsx"), /<CircularProgress size=\{10\}/);
});

// A BURST (the owner, 2026-11-05): a mail read in while turn 1 ran is drawn after it, stamped when it came in - the re-think under it began when
// turn 1 answered, the newest of everything above it, never at that mail's earlier stamp
test("a turn's run is counted from the newest thing above it, not the row just above", () => {
  const t = (hm) => new Date(`2026-11-05T17:${hm}`);
  assert.equal(+turnBegan([t("19:55"), t("21:10"), t("20:40")]), +t("21:10"));
  assert.equal(turnStamp({ start: turnBegan([t("19:55"), t("21:10"), t("20:40")]), end: t("21:50") }), "ran 40s");
  assert.equal(turnBegan([null, undefined]), null);
  assert.match(read("GeneralWorkspace.jsx"), /turnBegan\(ms\.slice\(0, i\)\.map\(\(m\) => m\.createdAt\)\)/);
});

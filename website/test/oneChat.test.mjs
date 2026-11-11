// ONE CHAT FOR EVERY TASK'S AGENT (the owner, 2026-11-06: "maybe one shared chat object for coding and regular but for coding default tool call
// backs are high and low for general agents, just summary though the settings can be changed. and diff shows up if there is branch or checkout
// stuff available. But combine the code as much as possible"). One mapper (chatStream.js) both sources feed, one component (GeneralWorkspace.jsx),
// three detail levels - and every chat fix of the day held in it. Invented people and repos only.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { chatSource, eventsOf, turnParts, workCount } from "../src/chatStream.js";
import { SHIPPED, defaultDetail, detailFor, keepOwnDetail, ownDetail } from "../src/chatDetail.js";

import { draftHome, draftPassed, freshNext, withTurns } from "../src/agentSummary.js";

const read = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const gw = read("GeneralWorkspace.jsx"), page = read("TaskPage.jsx");
const bare = (parts) => parts.map(({ id, ...p }) => (p.steps ? { ...p, steps: p.steps.map(({ id: _, detail, ...s }) => s) } : p));
const call = (id, name, args, extra = {}) => ({ type: "tool_call", name, detail: { tool_call_id: id, args, ...extra } });
const done = (id, result = "") => ({ type: "tool_result", name: id, detail: { tool_call_id: id, result } });
const words = (t) => ({ type: "progress", name: "text", detail: t });

// ── 1. one mapper, both sources ─────────────────────────────────────────────────────────────────
// the same turn, as a general agent's run trace and as a coding CLI's log
const TRACE = [call("a", "Read", { file_path: "C:/work/ledger/store.py" }), done("a"),
  call("b", "Bash", { command: "pytest -q tests" }), done("b", "3 passed"),
  call("c", "Edit", { file_path: "C:/work/ledger/budget.py", old_string: "total = a", new_string: "total = a + tax" }), done("c"),
  call("p", "TodoWrite", { todos: [{ content: "Read the ledger", status: "completed" }, { content: "Fix the tax line", status: "in_progress" }] }), done("p"),
  words("Fixed: the total now adds the tax line.")];
const LOG = [{ k: "brief", text: "TASKUARY: work TQ-0042 ..." },
  { k: "tool", name: "Read", args: { file_path: "C:/work/ledger/store.py" } },
  { k: "tool", name: "Bash", args: { command: "pytest -q tests" }, output: "3 passed" },
  { k: "tool", name: "Edit", args: { file_path: "C:/work/ledger/budget.py" }, file: "C:/work/ledger/budget.py", edit: { parts: [{ old: "total = a", new: "total = a + tax" }] } },
  { k: "plan", items: [{ text: "Read the ledger", status: "completed" }, { text: "Fix the tax line", status: "in_progress" }] },
  { k: "said", text: "Fixed: the total now adds the tax line." }];


test("a general agent that edits files gets its edit rows with diffs; a call that carries no diff stays a step", () => {
  const parts = turnParts([call("w", "Write", { file_path: "portal/new.js", content: "x\ny\n" }), done("w"),
    call("e", "Edit", { file_path: "portal/app.js" }), done("e")]);
  assert.deepEqual(parts.map((p) => p.type), ["edit", "work"]);
  assert.equal(parts[0].summary, "Wrote new.js (+2 −0)");
});


// ── 2. parallel work and helpers ────────────────────────────────────────────────────────────────
// the owner, 2026-11-06: "it's spinning but not the last thing … if it's still working why are we on next thing, shouldn't it be in order? unless
// it's in parallel"
test("a helper's own steps nest under its row, and while it runs alongside later steps it says so (run trace)", () => {
  const trace = [call("h", "Task", { description: "Check live portal pages" }),
    call("k1", "WebFetch", { url: "https://portal.example/status" }, { parent: "h" }), done("k1"),
    call("k2", "Grep", { pattern: "outage" }, { parent: "h" }), done("k2"),
    call("m", "Read", { file_path: "notes/status.md" }), done("m")];
  const [work] = turnParts(trace), [helper, main] = work.steps;
  assert.equal(work.steps.length, 2, "the helper's calls are not the main agent's");
  assert.equal(helper.status, "running"); assert.equal(helper.alongside, true);
  assert.deepEqual(helper.kids.map((s) => s.summary), ["Read portal.example/status", "Searched files for 'outage'"]);
  assert.equal(main.summary, "Read status.md");
  // ...and done, the spinner goes and the row says what it was and how much it did
  const [ended] = turnParts([...trace, done("h")]);
  assert.equal(ended.steps[0].summary, "Helper: Check live portal pages (done, 2 steps)");
  assert.equal(ended.steps[0].alongside, undefined);
});


// ── 3. the detail level ─────────────────────────────────────────────────────────────────────────
test("the detail level: Everything for coding work, Summary for other work, Settings' defaults, and a task's own choice over both", () => {
  assert.deepEqual(SHIPPED, { coding: "everything", other: "summary" });
  assert.equal(defaultDetail("coding"), "everything"); assert.equal(defaultDetail("general"), "summary");
  assert.equal(defaultDetail("coding", { chat_detail_coding: "steps" }), "steps");
  assert.equal(defaultDetail("general", { chat_detail_other: "nonsense" }), "summary", "an unknown value is the shipped default");
  assert.equal(detailFor({ source: "general", own: "everything" }), "everything");
  const kept = new Map(), events = [];
  globalThis.window = { localStorage: { getItem: (k) => kept.get(k) ?? null, setItem: (k, v) => kept.set(k, v), removeItem: (k) => kept.delete(k) },
    dispatchEvent: (e) => events.push(e.detail) };
  keepOwnDetail(42, "steps");
  assert.equal(ownDetail(42), "steps"); assert.equal(ownDetail(43), null, "per task");
  assert.deepEqual(events.at(-1), { tid: 42, level: "steps" });
  keepOwnDetail(42, null); assert.equal(ownDetail(42), null, "back to the default");
  globalThis.window = { get localStorage() { throw new Error("blocked"); }, dispatchEvent() {} };
  assert.equal(ownDetail(42), null, "blocked storage only loses the memory");
  delete globalThis.window;
  // ...Settings has the two, and every chat's corner draws the same slider
  const knobs = JSON.parse(fs.readFileSync(new URL("../../taskuary/settings_schema.json", import.meta.url), "utf8")).knobs;
  assert.equal(knobs.chat_detail_coding.type, "detail"); assert.equal(knobs.chat_detail_other.type, "detail");
  assert.match(read("SettingsView.jsx"), /if \(m\.type === "detail"\) return <DetailSlider /);
  assert.match(page, /<HeadPop id="chat-detail" title="Chat detail" .*?><ChatDetail taskId=\{t\.TaskId\} source=\{chatSource\(t, term\)\} \/><\/HeadPop>/);
});


test("a task's source is its sessions when it is coding or a coding CLI runs on it, else the general agent's conversation", () => {
  assert.equal(chatSource({ Kind: "coding" }, null), "coding");
  assert.equal(chatSource({ Kind: "general" }, { alive: true, mode: "pty" }), "coding");
  assert.equal(chatSource({ Kind: "general" }, { alive: true, mode: "assistant" }), "general");
  assert.equal(chatSource({ Kind: "reply" }, null), "general");
});






test("regression: strict arrival order - a later message draws below a step still running, and steps never reorder", () => {
  const parts = turnParts([words("Running the suite."), call("t", "Bash", { command: "pytest -q" }), words("Quick update: half of it passed.")]);
  assert.deepEqual(parts.map((p) => p.type), ["said", "work", "said"]);
  assert.equal(parts[1].steps[0].status, "running");
  // ...an edit between a call and its result leaves nothing it started spinning
  const cut = turnParts([call("t", "Bash", { command: "pytest -q" }), call("e", "Edit", { file_path: "a.py", old_string: "a", new_string: "b" }), done("e"), done("t")]);
  assert.deepEqual(cut.map((p) => p.type), ["work", "edit"]); assert.equal(cut[0].steps[0].status, "done");
});



test("regression: the owner's own ask gets no reply narration (server: tests/test_own_ask_no_reply.py, both sources' prompts)", () => {
  const py = fs.readFileSync(new URL("../../tests/test_own_ask_no_reply.py", import.meta.url), "utf8");
  assert.match(py, /def test_the_reply_tools_are_not_offered_on_the_owners_own_ask/);
  assert.match(py, /def test_the_coding_seed_says_there_is_nobody_to_reply_to/);
});

test("regression: an FYI handful says '6 messages', never 'nothing to decide'", () => {
  const cards = read("assistantCards.jsx");
  assert.doesNotMatch(cards, /`\$\{plural\(n, "message"\)\} - nothing to decide`|`\$\{plural\(n, "message"\)\} · nothing to decide`/);
  assert.match(cards, /title=\{batch \? plural\(n, "message"\) : card\.title\}/);
});


test("regression: one OneBox everywhere, with its paperclip and its mic", () => {
  assert.match(gw, /<OneBox root=\{ComposerPrimitive\.Root\}/);
  const one = read("AgentSummary.jsx"), box = one.slice(one.indexOf("export function OneBox"), one.indexOf("export const micInto"));
  assert.match(box, /className="tq-aui-attach"/); assert.match(box, /<MicButton /);
});

test("regression: the plan is one checklist, the newest of its turn", () => {
  const parts = turnParts([call("p1", "update_plan", { plan: ["Read the ledger", "Fix the tax line"] }), done("p1"),
    call("p2", "update_plan", { plan: [{ step: "Read the ledger", status: "completed" }, { step: "Fix the tax line", status: "in_progress" }] }), done("p2")]);
  assert.equal(parts.filter((p) => p.type === "plan").length, 1);
  assert.deepEqual(parts[0].items, [{ text: "Read the ledger", state: "done" }, { text: "Fix the tax line", state: "now" }]);
  assert.match(read("ViewSpec.jsx"), /<ul className="tq-cc-plan" data-tq-plan="" aria-label=\{label\}>/);
  assert.match(read("ViewSpec.jsx"), /PlanRow = \(\{ p, label = "The agent's plan" \}\)/);
});


test("regression: a nothing-new turn is one line", () => {
  assert.match(read("AgentSummary.jsx"), /if \(oneLine\(summary\)\) return <>\{<Box data-tq-summary="line"/);
});


test("regression: AI used and Talk to this agent from… sit in the header's corner, never at the chat's foot", () => {
  const head = page.slice(page.indexOf("<StatusPill status={status}"), page.indexOf("{onExpand && ("));
  assert.match(head, /<HeadPop id="ai-used" title="AI used"/);
  assert.match(head, /<HeadPop id="agent-channels" title="Talk to this agent from…"/);
  assert.doesNotMatch(gw, /<AgentChannels |<AiUsed /);
});




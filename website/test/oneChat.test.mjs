// ONE CHAT FOR EVERY TASK'S AGENT (the owner, 2026-11-06: "maybe one shared chat object for coding and regular but for coding default tool call
// backs are high and low for general agents, just summary though the settings can be changed. and diff shows up if there is branch or checkout
// stuff available. But combine the code as much as possible"). One mapper (chatStream.js) both sources feed, one component (GeneralWorkspace.jsx),
// three detail levels - and every chat fix of the day held in it. Invented people and repos only.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { chatSource, eventsOf, turnParts } from "../src/chatStream.js";
import { SHIPPED, defaultDetail, detailFor, keepOwnDetail, ownDetail } from "../src/chatDetail.js";


const read = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const gw = read("GeneralWorkspace.jsx"), page = read("TaskPage.jsx");

const call = (id, name, args, extra = {}) => ({ type: "tool_call", name, detail: { tool_call_id: id, args, ...extra } });
const done = (id, result = "") => ({ type: "tool_result", name: id, detail: { tool_call_id: id, result } });
const words = (t) => ({ type: "progress", name: "text", detail: t });


test("a general agent that edits files gets its edit rows with diffs; a call that carries no diff stays a step", () => {
  // ...the diff the call's own row carries (conversation.acp_of_trace: a Write's content is its diff) - the page reads no arguments for one
  const parts = turnParts([call("w", "Write", { file_path: "portal/new.js" }, { file: "portal/new.js", edit: { whole: true, parts: [{ old: "", new: "x\ny\n" }] } }), done("w"),
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
  assert.equal(ended.steps[0].summary, "Check live portal pages · 2 steps");
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
  const cut = turnParts([call("t", "Bash", { command: "pytest -q" }), call("e", "Edit", { file_path: "a.py" }, { file: "a.py", edit: { parts: [{ old: "a", new: "b" }] } }), done("e"), done("t")]);
  assert.deepEqual(cut.map((p) => p.type), ["work", "edit"]); assert.equal(cut[0].steps[0].status, "done");
});


// ...ONE ROW THE AGENT KEEPS REPLACING (chatlog: every plan update of a run is the one row s:<sid>:plan:<run>, tests/test_chatlog.py) - drawn as
// the checklist where it first stood
test("regression: the plan is one checklist, the newest of its turn", () => {
  const plan = { id: "s:x:plan:1", k: "plan", items: [{ text: "Read the ledger", status: "completed" }, { text: "Fix the tax line", status: "in_progress" }] };
  const parts = turnParts(eventsOf([plan], false));
  assert.equal(parts.filter((p) => p.type === "plan").length, 1);
  assert.deepEqual([parts[0].id, parts[0].items], ["s:x:plan:1", [{ text: "Read the ledger", state: "done" }, { text: "Fix the tax line", state: "now" }]]);
  assert.match(read("ViewSpec.jsx"), /<ul className="tq-cc-plan" data-tq-plan="" aria-label=\{label\}>/);
  assert.match(read("ViewSpec.jsx"), /PlanRow = \(\{ p, label = "The agent's plan" \}\)/);
});



// Section 1 of the task view (the redesign, 2026-10-16): the header's read-only "Triage decided" pills and "Came from",
// the task's messages as conversations, newest first - the latest two, what is between counted, and the first message.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { askLine, cameFromLabel, expands, groupConversations, groupMeta, headerFacts, hidden, latestRows, madeLine, previewRows, routeHead, startedBy, triageLine, workflowOrigin, workflowTitle } from "../src/taskSources.js";

const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
let id = 0;
const mail = (o) => ({ MessageId: ++id, Channel: "email", Status: "routed", Direction: "in", ...o });
const thread = (n, conv = "t-310") => Array.from({ length: n }, (_, i) => mail({ ConversationId: conv, Subject: i ? "RE: Export failing" : "Export failing",
  FromName: ["Backend monitor", "Ray Colton", "Paula Vance", "Gail Moreno"][i % 4], SentAt: `2026-10-${String(9 + Math.floor(i / 10)).padStart(2, "0")} 08:${String(i % 60).padStart(2, "0")}:00`,
  BodyText: `message ${i}` }));

test("messages group by conversation, newest first, with the thread's subject and who took part", () => {
  const ms = [...thread(5), mail({ ConversationId: "t-map", Subject: "Field mapping", FromName: "Paula Vance", SentAt: "2026-10-08 09:00:00", BodyText: "went live" }),
    { MessageId: ++id, Channel: "whatsapp", SourceName: "Northwind payroll group", FromName: "Erin Blake", SentAt: "2026-10-10 09:06:00", BodyText: "312 is out too" },
    { MessageId: ++id, Channel: "whatsapp", SourceName: "Northwind payroll group", Status: "context", SentAt: "2026-10-10 09:07:00", BodyText: "on it" }];
  const g = groupConversations(ms);
  assert.deepEqual(g.map((x) => x.title), ["Northwind payroll group", "Export failing", "Field mapping"], "the conversation that moved last leads");
  assert.equal(g[1].count, 5);
  assert.equal(g[1].people, 4);
  assert.equal(g[0].msgs[0].who, "You", "the latest line is on top, and your own line in a chat is yours");
  assert.equal(g[0].first.who, "Erin Blake", "first is still the message that started it");
  assert.equal(groupMeta(g[0]), "WhatsApp · 2 messages · 2 people");
  assert.equal(groupMeta(g[2]), "Email · 1 message");
  assert.equal(cameFromLabel(g), "Came from · 8 messages in 3 conversations");
  assert.equal(cameFromLabel(g.slice(0, 1)), "Came from · 2 messages");
});

test("a thread with no id still holds together by its subject, Re: and Fwd: taken off", () => {
  const g = groupConversations([mail({ Subject: "Invoice 41", SentAt: "2026-10-01" }), mail({ Subject: "RE: Fwd: Invoice 41", SentAt: "2026-10-02" }),
    mail({ Subject: "Something else", SentAt: "2026-10-03" })]);
  assert.deepEqual(g.map((x) => x.count), [1, 2], "Something else moved last, so it leads");
});

test("a long conversation shows the latest two on top, counts what is between and who wrote it, then the first message", () => {
  const [g] = groupConversations(thread(24));
  const rows = previewRows(g);
  assert.equal(rows.length, 4);
  assert.deepEqual(rows.slice(0, 2).map((r) => r.m.excerpt), ["message 23", "message 22"]);
  assert.equal(rows[2].gap, 21);
  assert.match(rows[2].names, /Ray Colton|Paula Vance|Gail Moreno|Backend monitor/);
  assert.equal(rows[3].m.excerpt, "message 0");
  assert.equal(previewRows(g, 2, true)[0].m.excerpt, "message 23", "Show all draws every one, newest first");
  assert.equal(previewRows(g, 2, true).length, 24);
  assert.equal(hidden([g]), 21);
});

test("a short conversation is shown whole - a gap of one is not worth a line", () => {
  const [g] = groupConversations(thread(4, "short"));
  assert.equal(previewRows(g).length, 4);
  assert.ok(previewRows(g).every((r) => r.m));
  assert.equal(hidden([g]), 0);
});

// Close out's condensed view of the conversation it answers: the latest four, newest first, then what is under them counted
test("Close out reads the latest four, newest first, and counts the rest", () => {
  const [g] = groupConversations(thread(24, "close"));
  const rows = latestRows(g);
  assert.deepEqual(rows.slice(0, 4).map((r) => r.m.excerpt), ["message 23", "message 22", "message 21", "message 20"]);
  assert.equal(rows[4].gap, 20);
  assert.equal(rows.length, 5, "no first message under the gap - the draft answers the top line");
  assert.equal(latestRows(groupConversations(thread(5, "five"))[0]).length, 5, "a gap of one is not worth a line");
});

test("Show all is offered for a hidden middle, or for any chat of more than one line - its bubbles", () => {
  const chat = (n) => groupConversations(Array.from({ length: n }, (_, i) => ({ MessageId: ++id, Channel: "whatsapp", SourceName: "Northwind payroll group",
    FromName: i % 2 ? "Erin Blake" : "Gail Moreno", SentAt: `2026-10-15 09:0${i}:00`, BodyText: `line ${i}` })));
  assert.ok(expands(chat(3)));
  assert.ok(!expands(chat(1)));
  assert.ok(!expands(groupConversations(thread(4, "short2"))));
  assert.ok(expands(groupConversations(thread(9, "long"))));
});

test("the ask is one line: its first sentence, the rest kept for the tooltip", () => {
  assert.deepEqual(askLine("Erin wants the Monday invite sent. She also asks about presets."), { line: "Erin wants the Monday invite sent.", cut: true });
  assert.deepEqual(askLine("Fix the export"), { line: "Fix the export", cut: false });
  assert.equal(askLine("").line, "");
  assert.ok(askLine("word ".repeat(100)).line.endsWith("…"));
});

test("the header says what triage decided, and the task's own facts when triage never saw it", () => {
  const general = headerFacts({ verdict: { intent: "task", kind: "general" }, task: { Kind: "general", Assignee: "agent:assistant", Priority: "normal" } });
  assert.equal(general.triaged, true);
  assert.deepEqual(general.pills.map((p) => [p.label, p.value]),
    [["What it is", "task"], ["Who does it", "an agent"], ["Agent", "assistant"], ["Priority", "normal"]]);
  const coding = headerFacts({ verdict: { intent: "task" }, task: { Kind: "coding", Tags: "triage-repo:northwind/ledger", Priority: "urgent" } });
  assert.deepEqual(coding.pills.map((p) => p.value), ["task", "a coding agent", "northwind/ledger", "urgent"]);
  assert.equal(coding.pills.at(-1).tone, "alert", "urgent wears the alert tint");
  assert.equal(coding.pills.find((p) => p.key === "repo").mono, true);
  // the owner's own pick of checkout outranks triage's
  assert.equal(headerFacts({ task: { Kind: "coding", Tags: "repo:northwind/portal,triage-repo:northwind/ledger" } }).pills.find((p) => p.key === "repo").value, "northwind/portal");
  const reply = headerFacts({ route: { Reason: "triage: needs a reply - she asks when" }, task: { Kind: "reply" } });
  assert.deepEqual(reply.pills.slice(0, 2).map((p) => p.value), ["reply", "yours"]);
  assert.deepEqual(headerFacts({ task: { Kind: "coding", Tags: "held:repo" } }).pills.find((p) => p.key === "repo"),
    { key: "repo", label: "Repository", value: "none - not started", tone: "alert" }, "a start held for a repository says so");
  const byHand = headerFacts({ task: { Kind: "task", Priority: "low" } });
  assert.equal(byHand.triaged, false, "no label claims triage decided a task you made");
  assert.deepEqual(byHand.pills.map((p) => p.value), ["yours", "low"]);
  assert.ok(!headerFacts({ task: { Kind: "coding", Assignee: "agent:assistant" } }).pills.some((p) => p.key === "profile"), "a profile is a general task's");
});

test("the triage line leads with whose it is, in the new wording and the old", () => {
  assert.equal(routeHead("triage: work for the coding agent in northwind/ledger - a code failure"), "work for the coding agent in northwind/ledger");
  assert.equal(routeHead("triage: task - asks for X", { kind: "coding", repo: "org/app" }), "work for a coding agent in org/app");
  assert.equal(routeHead("triage: task - asks for X", { kind: "task" }), "yours to do");
  assert.equal(routeHead("triage: fyi - newsletter"), "nothing to do");
  const route = { MessageId: 1, Reason: "triage: work for the assistant - Erin asks you to send the invite · rank 3", CreatedAt: "2026-10-16 09:07:00" };
  const line = triageLine({ route, task: { Kind: "general", CreatedAt: "2026-10-16 09:07:00" },
    messages: [{ MessageId: 1, CreatedAt: "2026-10-16 09:06:00" }, { MessageId: 2, CreatedAt: "2026-10-16 10:00:00" },
      { MessageId: 3, Status: "context", CreatedAt: "2026-10-16 10:05:00" }] });
  assert.deepEqual(line, { later: 1, head: "work for the assistant", why: "Erin asks you to send the invite", at: "2026-10-16 09:07:00" });
  assert.equal(triageLine({ route, verdict: { why: "the verdict's own words" }, task: {} }).why, "the verdict's own words");
  assert.equal(triageLine({ route: { Reason: "triage: task" }, task: {} }).why, "", "a head alone has no why");
  assert.deepEqual(triageLine({ task: {} }), { later: 0, head: "", why: "", at: "" });
  // a route that created the task, from before the heads: triage still decided it, and the line says whose it made it
  const old = { MessageId: 1, Decision: "create", Reason: "a request with a list and a date", CreatedAt: "2026-10-16 09:00:00" };
  assert.equal(headerFacts({ route: old, task: { Kind: "general" } }).triaged, true);
  assert.deepEqual(triageLine({ route: old, task: { Kind: "general" } }), { later: 0, head: "work for an agent", why: "a request with a list and a date", at: "2026-10-16 09:00:00" });
  assert.equal(headerFacts({ route: { Decision: "attach", Reason: "same conversation thread" }, task: { Kind: "task" } }).triaged, false, "joining a thread decides nothing");
});

test("the task view draws the new section: read-only pills, no in-section buttons, no Where this came from", () => {
  assert.match(page, /from "\.\/taskSources\.js"/);
  assert.ok(page.includes("Sorted as: "), "triage's facts said as one plain line (the audit, 2026-10-17)");
  assert.ok(!page.includes(">Triage decided<"));
  assert.doesNotMatch(page, /Where this came from\s*<\/Button>/, "the disclosure is gone - Came from replaces it");
  assert.ok(!page.includes("setSourceOpen"));
  assert.ok(!page.includes("sx={chipSel}"), "no dropdowns by the triage results");
  // each part named in its own column, so the three read as separate parts with no rule between them
  for (const part of ["The ask", "To do", "Came from"]) assert.ok(page.includes(`<Part label="${part}"`), `${part} is its own part`);
  assert.match(page, /verdict\?\.summary \|\| t\?\.Summary/, "the ask is triage's summary first");
  assert.match(page, /maxHeight: THREAD_MAX, overflowY: "auto"/, "Show all scrolls when it goes far back");
  // ...in a box as tall as the window leaves, never the 360px that held three lines of seven (the owner, 2026-10-20)
  assert.match(page, /const THREAD_MAX = "max\(360px, calc\(100vh - 160px\)\)";/);
  assert.doesNotMatch(page, /maxHeight=\{360\}|showAll \? \{ maxHeight: 360/);
  // the edits the pills offered are reachable from the bar: kind, priority, who, repository
  for (const id of ["kind", "priority", "assign"]) assert.ok(page.includes(`{ id: "${id}", group: "more"`), `the row carries ${id}`);
  // the repository is a More item too - and the row's own move while a start is held for it
  assert.ok(page.includes(`{ id: "repo", group: heldRepo ? "decide" : "more"`), "the row carries repo");
});

// A WORKFLOW RUN (workflows.run): no message, never triaged - the header says which workflow and what started it, and Came from
// says the same where a message would be (the owner, 2026-10-16: "what's the logo on it and what does it show triggered it?")
test("a workflow run's header names the workflow and who started it, never Triage decided", () => {
  const wf = { source_id: 7, title: "Vendor bill sweep", trigger: "schedule", schedule: "Mondays 08:00", started_by: "its schedule" };
  const task = { Kind: "general", Source: "workflow", SourceRef: "workflow:7", Tags: "workflow-trigger:schedule", Assignee: "agent:ap",
    Title: "Vendor bill sweep - 2026-10-12 08:00" };
  const facts = headerFacts({ task, workflow: wf, route: { Decision: "create", Reason: "triage: task" } });
  assert.equal(facts.triaged, false, "nobody triaged it, whatever a stray route says");
  assert.equal(facts.workflow, true);
  assert.deepEqual(facts.pills.slice(0, 2).map((p) => [p.label, p.value]),
    [["Workflow", "Vendor bill sweep"], ["Started by", "its schedule (Mondays 08:00)"]]);
  assert.ok(!facts.pills.some((p) => p.key === "intent"));
  assert.deepEqual(facts.pills.slice(2).map((p) => p.value), ["an agent", "ap", "normal"]);
  // the list row has no detail: the tag alone still says who started it, and the run's own title still names the workflow
  assert.equal(startedBy({ Tags: "needs:browser,workflow-trigger:manual" }), "you (Run now)");
  assert.equal(startedBy({ Tags: "workflow-trigger:assistant" }), "the assistant");
  assert.equal(startedBy({ Tags: "workflow-trigger:phone" }), "you, from your phone");
  assert.equal(startedBy({ Tags: "workflow-trigger:schedule" }), "its schedule", "no clock to name without the detail");
  assert.equal(workflowTitle({ Title: "Vendor bill sweep - 2026-10-12 08:00" }), "Vendor bill sweep");
  assert.equal(headerFacts({ task: { ...task, Tags: "" }, workflow: null }).pills.find((p) => p.key === "trigger"), undefined,
    "a run from before the tag says nothing it does not know");
});

test("where a task came from is said in plain words - sorted, made by you - never 'created ... by triage'", () => {
  assert.equal(madeLine({ Source: "email", CreatedBy: "triage" }, "1m ago"), "from email · sorted 1m ago");
  assert.equal(madeLine({ Source: "manual", CreatedBy: "owner" }, "2h ago"), "made by you 2h ago");
  assert.equal(madeLine({ Source: "github", CreatedBy: "ci" }, "now"), "from github · made now");
  assert.match(page, /const made = t \? madeLine\(t, timeAgo\(t\.CreatedAt\)\) : "";/);
  assert.doesNotMatch(page, /created \$\{timeAgo/);
});

test("a workflow run's Came from is the workflow and its trigger, with the way back to it", () => {
  const task = { Kind: "coding", Source: "workflow", Tags: "workflow-trigger:manual", Title: "Dependency bumps - 2026-10-16 09:30" };
  assert.deepEqual(workflowOrigin(task, { source_id: 9, title: "Dependency bumps", trigger: "manual", started_by: "you (Run now)" }),
    { title: "Dependency bumps", by: "you (Run now)", line: "Started by you (Run now)", link: "#report=9" });
  assert.deepEqual(workflowOrigin({ ...task, Tags: "" }, null), { title: "Dependency bumps", by: "", line: "A workflow run", link: "" },
    "the workflow deleted: the run still says what it was");
  assert.equal(workflowOrigin({ Source: "email" }), null);
  assert.ok(page.includes("workflowOrigin("), "the page draws it");
  assert.ok(page.includes('channel="workflow"'), "with the workflow's own mark, as the Reports shelf draws it");
});

test("the Tasks list says a row is a workflow run and who started it", () => {
  const list = fs.readFileSync(new URL("../src/TasksView.jsx", import.meta.url), "utf8");
  assert.ok(list.includes("isWorkflowRun(task)") && list.includes("started by ${startedBy(task)}"));
});

test("a workflow run's header says the model and effort it runs on", () => {
  const task = { Kind: "general", Source: "workflow", Tags: "workflow-trigger:manual", Title: "Month-end accruals - 2026-10-16 09:30" };
  const facts = headerFacts({ task, workflow: { title: "Month-end accruals", trigger: "manual", started_by: "you (Run now)", runs_on: "Claude Code · opus, high effort" } });
  assert.deepEqual(facts.pills.find((p) => p.key === "runs_on"), { key: "runs_on", label: "Runs on", value: "Claude Code · opus, high effort", tone: "agent" });
  assert.equal(headerFacts({ task: { Kind: "general", Source: "email" }, workflow: { runs_on: "x" } }).pills.find((p) => p.key === "runs_on"), undefined);
});

test("a run of steps with no agent step names no agent: its steps do it, and the task has no Agent work to open", () => {
  const task = { Kind: "general", Source: "workflow", Tags: "workflow-trigger:manual", Title: "Duplicate bill check - 2026-10-18 09:30" };
  const wf = { title: "Duplicate bill check", runs_on: "", by_code: true, steps: [{ id: "s1", kind: "source", status: "ok" }], source_id: 4, run_id: 9 };
  const pills = headerFacts({ task, workflow: wf }).pills;
  assert.equal(pills.find((p) => p.key === "runs_on"), undefined);
  assert.equal(pills.find((p) => p.key === "who").value, "its steps");
  assert.equal(workflowOrigin(task, wf).byCode, true);
  assert.equal(workflowOrigin(task, { ...wf, by_code: false }).byCode, undefined);
});

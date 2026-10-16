// Section 1 of the task view (the redesign, 2026-10-16): the header's read-only "Triage decided" pills and "Came from",
// the task's messages as conversations, newest first - the latest two, what is between counted, and the first message.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { askLine, cameFromLabel, groupConversations, groupMeta, headerFacts, hidden, previewRows, routeHead, triageLine } from "../src/taskSources.js";

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
    [["Intent", "task"], ["Who does it", "an agent · general"], ["Profile", "assistant"], ["Priority", "normal"]]);
  const coding = headerFacts({ verdict: { intent: "task" }, task: { Kind: "coding", Tags: "triage-repo:northwind/ledger", Priority: "urgent" } });
  assert.deepEqual(coding.pills.map((p) => p.value), ["task", "an agent · coding", "northwind/ledger", "urgent"]);
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
  assert.equal(routeHead("triage: task - asks for X", { kind: "coding", repo: "org/app" }), "work for the coding agent in org/app");
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
  assert.deepEqual(triageLine({ route: old, task: { Kind: "general" } }), { later: 0, head: "work for the assistant", why: "a request with a list and a date", at: "2026-10-16 09:00:00" });
  assert.equal(headerFacts({ route: { Decision: "attach", Reason: "same conversation thread" }, task: { Kind: "task" } }).triaged, false, "joining a thread decides nothing");
});

test("the task view draws the new section: read-only pills, no in-section buttons, no Where this came from", () => {
  assert.match(page, /from "\.\/taskSources\.js"/);
  assert.ok(page.includes("Triage decided"));
  assert.doesNotMatch(page, /Where this came from\s*<\/Button>/, "the disclosure is gone - Came from replaces it");
  assert.ok(!page.includes("setSourceOpen"));
  assert.ok(!page.includes("sx={chipSel}"), "no dropdowns by the triage results");
  // each part named in its own column, so the three read as separate parts with no rule between them
  for (const part of ["The ask", "To do", "Came from"]) assert.ok(page.includes(`<Part label="${part}"`), `${part} is its own part`);
  assert.match(page, /verdict\?\.summary \|\| t\?\.Summary/, "the ask is triage's summary first");
  assert.match(page, /maxHeight: 360, overflowY: "auto"/, "Show all scrolls when it goes far back");
  // the edits the pills offered are reachable from the bar: kind, priority, who, repository
  for (const id of ["kind", "priority", "assign", "repo"]) assert.ok(page.includes(`{ id: "${id}", group: "more"`), `the row carries ${id}`);
});

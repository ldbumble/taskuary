// A workflow as steps (taskuary/flow.py): the editor's rules, as plain functions. Invented people only.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { asReport, asSteps, askFor, badRefs, onlyReads, diffKeys, firstMissing, insertStep, isLoneAgent, moveStep, nextId, outputsOf, removeStep,
  runWords, stepsOf, tally, toSaved, tokenInQuery, tokensFor } from "../src/workflowFlow.js";
import { demoRepair, demoStepTest, installDemoWorkflows, PAYROLL } from "../src/demoWorkflows.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
const flow = [
  { id: "s1", kind: "source", label: "Read AP bills", type: "mssql", query: "SELECT 1" },
  { id: "s2", kind: "ai", label: "Duplicates?", prompt: "{{s1}}", output: "yes_no" },
  { id: "s3", kind: "task", label: "Tell finance", title: "{{s2.why}}", only_if: { step: "s2", is: "yes" } },
];

test("a workflow saved before steps is one agent step, and shows as the one prompt it always was", () => {
  assert.deepEqual(stepsOf({ prompt: "Post the approved bills", skill: "ap" }),
    [{ id: "s1", kind: "agent", label: "Agent works it", prompt: "Post the approved bills", skill: "ap" }]);
  assert.equal(asSteps({ prompt: "x" }), false);
  assert.equal(asSteps({ flow: [] }), true);                      // building it by hand starts from an empty list
  assert.equal(asSteps({ flow: [{ id: "s1", kind: "agent", prompt: "x" }] }), false);
  assert.equal(isLoneAgent(flow), false);
});

test("ids are never reused, and a new step goes above the agent step", () => {
  assert.equal(nextId(flow), "s4");
  assert.equal(nextId([{ id: "s7" }, { id: "s2" }]), "s8");
  const withAgent = insertStep(flow, 3, "agent");
  assert.equal(withAgent.at(-1).kind, "agent");
  assert.equal(insertStep(withAgent, 9, "agent").length, withAgent.length);          // one agent, always last
  const added = insertStep(withAgent, 9, "draft");
  assert.deepEqual(added.map((s) => s.kind), ["source", "ai", "task", "draft", "agent"]);
  assert.equal(added[3].id, "s5");
});

test("moving or removing a step never leaves an only-if pointing at a step below it, or at nothing", () => {
  const up = moveStep(flow, 2, -1);
  assert.deepEqual(up.map((s) => s.id), ["s1", "s3", "s2"]);
  assert.equal(up[1].only_if, undefined);
  assert.equal(removeStep(flow, 1).find((s) => s.id === "s3").only_if, undefined);
  assert.deepEqual(moveStep([...flow, { id: "s4", kind: "agent", prompt: "p" }], 3, -1).map((s) => s.id), ["s1", "s2", "s3", "s4"]);
});

test("Insert output offers only the steps above, in the words of what each hands on", () => {
  const menu = tokensFor(flow, 2);
  assert.deepEqual(menu.map((g) => g.id), ["s1", "s2"]);
  assert.deepEqual(menu[0].tokens.map(([t]) => t), ["{{s1}}", "{{s1.rows}}", "{{s1.head}}"]);
  assert.deepEqual(menu[1].tokens.map(([t]) => t), ["{{s2.answer}}", "{{s2.why}}"]);
  assert.deepEqual(tokensFor([{ id: "s1", kind: "ai", output: "fields", fields: ["vendor"] }], 1)[0].tokens.map(([t]) => t), ["{{s1.fields.vendor}}"]);
  assert.deepEqual(badRefs(flow, 1), []);
  assert.deepEqual(badRefs([{ id: "s1", kind: "task", title: "{{s2.head}} {{inputs.site}}" }], 0), ["s2"]);
  assert.deepEqual(badRefs([flow[0], { id: "s2", kind: "task", title: "{{read ap bills.rows}}" }], 1), []);   // by label too
  assert.equal(tokenInQuery({ kind: "source", query: "WHERE x = '{{s1.head}}'" }), true);
});

test("a step with something left to fill in is named before Save", () => {
  assert.equal(firstMissing(flow), "");
  assert.equal(firstMissing([...flow, { id: "s4", kind: "draft", to: "gail@northwind.example" }]), "step 4 needs what it is about");
  assert.equal(firstMissing([{ id: "s1", kind: "ai", prompt: "p", output: "fields", fields: [] }]), "step 1 needs the fields it fills");
});

test("a source step is saved in the executor's shapes, its empties dropped", () => {
  const [s] = toSaved([{ id: "s1", kind: "source", label: "", type: "intacct", object: "APBILL", fields: "VENDORID, TOTALDUE", max_rows: "50", query: "" }]);
  assert.deepEqual(s, { id: "s1", kind: "source", label: "Read/write a system", type: "intacct", object: "APBILL", fields: ["VENDORID", "TOTALDUE"], max_rows: 50 });
});

test("a run reads back in the owner's words, and says how little AI it took", () => {
  const recs = [{ id: "s1", kind: "source", status: "ok", ms: 800 }, { id: "s2", kind: "task", status: "ok", ms: 1300 }, { id: "s3", kind: "ai", status: "skipped" }];
  assert.equal(tally(recs), "Ran 2 steps in 2.1s, no AI used");
  assert.equal(runWords([...recs.slice(0, 1), { id: "s2", kind: "source", status: "failed", error: "Invalid object name" }]), "Step 2 failed: Invalid object name");
  assert.equal(runWords([{ id: "s1", kind: "source", status: "waiting" }]), "Waiting for your yes on step 1");
  // a step repaired twice and still failing is step 1, and the repairs were the AI it took
  const tried = [{ id: "s1", kind: "source", status: "repaired", ms: 1 }, { id: "s1", kind: "source", status: "repaired", ms: 1 }];
  assert.equal(runWords([...tried, { id: "s1", kind: "source", status: "failed", error: "gone" }], true), "Step 1 failed");
  assert.equal(tally([...tried, { id: "s1", kind: "source", status: "ok", ms: 8 }]), "Ran 1 step in 0.0s, AI only for the repair");
  assert.deepEqual(Object.keys(outputsOf(recs)), ["s1", "s2", "s3"]);
});

test("a repair not yet kept marks exactly the keys it changed", () => {
  const now = [{ ...flow[0], query: "SELECT 2" }, flow[1], flow[2], { id: "s4", kind: "task", title: "new" }];
  const d = diffKeys(flow, now);
  assert.deepEqual(Object.keys(d), ["s1", "s4"]);
  assert.deepEqual([...d.s1], ["query"]);
  assert.deepEqual([...d.s4], ["*"]);
});

test("Turn into steps asks with what the workflow already says", () => {
  const ask = askFor({ title: "Duplicate bills", prompt: "Find bills posted twice.", uses: [7], ask_first: "voiding anything" }, { 7: "Northwind AP" });
  assert.match(ask, /^Duplicate bills\. Find bills posted twice\. It works in: Northwind AP\. Ask first before: voiding anything\./);
  assert.match(ask, /Build it as steps/);
});

test("the editor shows steps in place of What it does, and keeps the old field with Turn into steps", () => {
  const ed = read("WorkflowEditor.jsx");
  assert.match(ed, /\{steps \? <Field label="Steps"/);
  assert.ok(ed.includes('"Turn into steps"') && ed.includes("/api/workflows/compose") && ed.includes("/repair`"));
  assert.ok(ed.includes('"When a step fails"'));
  const st = read("WorkflowSteps.jsx");
  assert.ok(st.includes("/api/workflows/step-test") && st.includes('"Test this step"') && st.includes("Insert output of"));
  assert.ok(read("ReportsView.jsx").includes("export function SourceCard"));
  assert.ok(read("TaskPage.jsx").includes("<RunSteps steps={fromWorkflow.steps} dense repairs={fromWorkflow.repairs}"));
});

// a self-repair is a record - what broke, why, what changed - with no Take it back (the owner, 2026-10-19); the step editor changes it back
test("a self-repair reads back with what broke and what changed, in the shared button words", () => {
  const rs = read("RunSteps.jsx");
  assert.ok(rs.includes('btnLabel("fix")') && rs.includes("Repaired itself") && !rs.includes("take_back") && !rs.includes("/undo-repair"));
  assert.doesNotMatch(rs, />Fix with AI</);
  assert.equal(tally([{ kind: "source", status: "repaired", ms: 300 }, { kind: "source", status: "ok", ms: 700 }]), "Ran 1 step in 1.0s, AI only for the repair");
  assert.ok(read("WorkflowEditor.jsx").includes('cfg.repair || "auto"'));                 // repair is on unless the owner says otherwise
});

test("steps that only read are a report: the editor offers it, built from the same query and prompt", () => {
  const types = [{ type: "mssql", writes: false }, { type: "smb_write", writes: true }];
  const reads = [flow[0], { id: "s2", kind: "ai", label: "Summary", prompt: "Summarize:\n{{s1}} ({{s1.rows}} rows)", output: "text" }];
  assert.equal(onlyReads(reads, types), true);
  assert.equal(onlyReads(flow, types), false);                                                  // it opens a task
  assert.equal(onlyReads([{ id: "s1", kind: "source", type: "smb_write" }], types), false);
  assert.equal(onlyReads([{ id: "s1", kind: "source", type: "unheard_of" }], types), false);     // not vouched for: counts as a write
  assert.deepEqual(asReport({ title: "Bills", cron: "0 8 * * 1", flow: reads }),
    { title: "Bills", ai_prompt: "Summarize:\n[mssql.read ap bills] ( rows)", cron: "0 8 * * 1", type: "mssql", query: "SELECT 1", label: "Read AP bills" });
  const ed = read("WorkflowEditor.jsx");
  assert.match(ed, /onlyReads\(cfg\.flow, types\) && <Alert[^>]*data-tq-report-suggestion/);
  assert.match(ed, /onReport\(asReport\(cfg\)\)}>\{btnLabel\("make_report"\)\}</);
  assert.match(read("Composer.jsx"), /out\?\.verdict === "report"[\s\S]*btnLabel\("make_report"\)/);
  assert.match(read("ReportsView.jsx"), /meta\?\.verdict === "report" \? asReportDraft\(config, meta\)/);
});

test("the demo world has a clean run and a failed one, and its step test never writes", () => {
  const state = {};
  installDemoWorkflows(state);
  const flows = state["/api/sources"].data.map((s) => JSON.parse(s.ConfigJson));
  assert.equal(flows.length, 2);
  assert.ok(flows.every((c) => c.flow.length >= 3));
  assert.equal(state["/api/reports/last-runs"].data[PAYROLL].failed, true);
  const payroll = flows[1].flow;
  assert.equal(demoStepTest({ flow: payroll, index: 1 }).status, "dry");                 // the share write
  assert.equal(demoStepTest({ flow: payroll, index: 2 }).status, "dry");                 // the task
  assert.equal(demoStepTest({ flow: payroll, index: 0 }).status, "failed");
  const fixed = demoRepair(state, PAYROLL);
  assert.match(fixed.flow[0].query, /payroll_exports/);
  // invented people and reserved domains only (CLAUDE.md)
  const text = JSON.stringify(state);
  for (const m of text.matchAll(/[a-z0-9.-]+@([a-z0-9.-]+)/gi)) assert.match(m[1], /\.example$/);
});

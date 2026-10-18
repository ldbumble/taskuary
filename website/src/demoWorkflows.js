// Two workflows built as steps (taskuary/flow.py), for the demo world - invented like everything in it. One ran clean on its
// schedule: a SQL read, one AI judgement, a task and a draft. One failed at its first step, so Fix with AI has something to fix.
// The editor's Test this step answers here as the server would: reads and AI steps come back with output, writes come back dry.
import { fmtStamp } from "./demoClock.js";

export const DUPES = 901, PAYROLL = 902, DUPES_TASK = 61;
const ago = (min) => fmtStamp(Date.now() - min * 60000);
const ROWS = '{"vendor": "Payworth", "invoice_no": "PW-20931", "amount": 1840.0, "n": 2}\n{"vendor": "Trainly", "invoice_no": "TR-4471", "amount": 412.5, "n": 2}';
const OLD_SQL = "SELECT vendor, invoice_no, amount, COUNT(*) n\nFROM ap_bill\nWHERE posted >= DATEADD(day, -7, GETDATE())\nGROUP BY vendor, invoice_no, amount\nHAVING COUNT(*) > 1";
const DUPE_SQL = OLD_SQL.replace("posted >=", "posted_at >=");

const dupesFlow = [
  { id: "s1", kind: "source", label: "Read last week's AP bills", type: "mssql", connector_id: 951, query: DUPE_SQL },
  { id: "s2", kind: "ai", label: "Real duplicates?", output: "yes_no",
    prompt: "These bills share a vendor, invoice number and amount. Are any of them real duplicates rather than a reissued invoice?\n{{s1}}" },
  { id: "s3", kind: "task", label: "Open a task for finance", title: "Duplicate bills to void: {{s1.rows}} pairs", summary: "{{s2.why}}\n\n{{s1}}",
    only_if: { step: "s2", is: "yes" } },
  { id: "s4", kind: "draft", label: "Email Gail the pairs", channel: "email", to: "gmoreno@northwind.example", subject: "Duplicate bills this week",
    about: "Tell Gail which bills were posted twice last week and that a task is open to void them ({{s3.head}}):\n{{s1}}", only_if: { step: "s2", is: "yes" } },
];
const payrollFlow = [
  { id: "s1", kind: "source", label: "Read the payroll export", type: "mssql", connector_id: 951,
    query: "SELECT employee_id, period, gross FROM payroll_export WHERE period = '{{run.date}}'" },
  { id: "s2", kind: "source", label: "File it on the share", type: "smb_write", path: "Payroll/exports/{{run.date}}.csv" },
  { id: "s3", kind: "task", label: "Tell payroll it is filed", title: "Payroll export filed for {{run.date}}", summary: "{{s1.rows}} rows, on the share." },
];

// the clean run met a renamed column first, and repaired that step itself - the goal was the same (flow.repair)
const dupesRepair = () => ({ at: ago(96), step: "s1", label: "Read last week's AP bills", undone: false,
  error: "('42S22', \"[SQL Server]Invalid column name 'posted'. (207)\")", why: "The posted column was renamed posted_at - the same bills, read the same way.",
  diff: [{ id: "s1", label: "Read last week's AP bills", change: "changed", keys: [{ key: "query", was: OLD_SQL, now: DUPE_SQL }] }] });
const dupesRun = () => [
  { id: "s1", label: "Read last week's AP bills", kind: "source", status: "repaired", ms: 290, head: "failed, then repaired", error: dupesRepair().error },
  { id: "s1", label: "Read last week's AP bills", kind: "source", status: "ok", ms: 840, head: "2 rows", rows: 2, body: ROWS },
  { id: "s2", label: "Real duplicates?", kind: "ai", status: "ok", ms: 1260, answer: true, why: "Both pairs were posted on the same day by the same user - neither is a reissue.",
    head: "yes - Both pairs were posted on the same day by the same user - neither is a reissue.", body: '{"answer": true, "why": "Both pairs were posted on the same day by the same user - neither is a reissue."}' },
  { id: "s3", label: "Open a task for finance", kind: "task", status: "ok", ms: 12, head: "TQ-0062", ref: "TQ-0062", body: "Duplicate bills to void: 2 pairs" },
  { id: "s4", label: "Email Gail the pairs", kind: "draft", status: "ok", ms: 2210, head: "draft for gmoreno@northwind.example",
    body: "Hi Gail,\n\nTwo bills were posted twice last week - Payworth PW-20931 (1,840.00) and Trainly TR-4471 (412.50). TQ-0062 is open to void the second copy of each.\n\nAlex" },
];
const payrollRun = () => [
  { id: "s1", label: "Read the payroll export", kind: "source", status: "failed", ms: 310, head: "failed",
    error: "('42S02', \"[Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Invalid object name 'payroll_export'. (208)\")" },
];
const words = (recs) => {
  const bad = recs.findIndex((r) => r.status === "failed");
  if (bad >= 0) return `Step ${bad + 1} failed: ${recs[bad].error} Fix it on the workflow, or change the step by hand.`;
  const ran = recs.filter((r) => r.status !== "repaired");
  return `Ran ${ran.length} steps in ${(recs.reduce((n, r) => n + r.ms, 0) / 1000).toFixed(1)}s, ${ran.filter((r) => ["ai", "draft", "agent"].includes(r.kind)).length} with AI`;
};
const runRec = (sid, title, runId, task, recs, at) => ({ at, type: "flow", title, trigger: "schedule", subject: `${title} → TQ-00${task} (steps)`, task_id: task,
  run_id: runId, steps: recs, ms: recs.reduce((n, r) => n + r.ms, 0), failed: recs.some((r) => r.status === "failed"),
  error: recs.some((r) => r.status === "failed") ? `step 1 ${recs[0].label}: ${recs[0].error}` : null, summary: words(recs) });
const row = (r, sid) => ({ runId: r.run_id, sourceId: sid, at: r.at, type: "flow", title: r.title, ms: r.ms, subject: r.subject, messageId: null, failed: r.failed,
  error: r.error, said: 0, lines: [], reviewed: null, inputChars: 0, steps: r.steps, repairs: r.repairs || [], taskId: r.task_id, summary: r.summary, inputs: "" });

// the recording predates the `writes` flag on /api/report-types (flow.writes): the demo says it for the types its steps use
const DEMO_WRITES = new Set(["smb_write", "smb_move", "sftp_put", "sftp_move", "intacct_create", "intacct_update", "quickbooks_bill", "quickbooks_expense",
  "mcp", "winrm", "agent", "assistant", "taskuary", "handbook_write", "hub_write", "kb_reindex"]);

export function installDemoWorkflows(state) {
  for (const t of state["/api/report-types"]?.data || []) if (t.writes === undefined) t.writes = DEMO_WRITES.has(t.type);
  const conns = (state["/api/connectors"] ||= { data: [] }).data;
  if (!conns.some((c) => c.ConnectorId === 951))
    conns.push({ ConnectorId: 951, Type: "mssql", Name: "Northwind AP database", Active: 1, LastSyncAt: ago(30), LastError: null, Scope: "write", HasSecret: true, ConfigJson: "{}" });
  const sources = (state["/api/sources"] ||= { data: [] }).data;
  const add = (sid, title, cfg, at) => sources.push({ SourceId: sid, Channel: "report", Address: title, Owner: "owner", Active: 1, LastPolledAt: at,
    ConfigJson: JSON.stringify({ type: "agent", access: "write", agent: "assistant", title, ...cfg }) });
  const a = runRec(DUPES, "Duplicate vendor bills", 9011, DUPES_TASK, dupesRun(), ago(95));
  const b = runRec(PAYROLL, "Payroll export to the share", 9021, 63, payrollRun(), ago(40));
  add(DUPES, "Duplicate vendor bills", { cron: "0 7 * * 1", flow: dupesFlow, done_when: "a task per run with duplicates; nothing when there are none" }, a.at);
  add(PAYROLL, "Payroll export to the share", { cron: "0 6 * * 5", flow: payrollFlow, repair: "propose" }, b.at);
  const last = (state["/api/reports/last-runs"] ||= { data: {} }).data;
  a.repairs = [dupesRepair()]; a.summary = `${a.summary}; repaired itself once`;
  last[DUPES] = a; last[PAYROLL] = b;
  state[`/api/reports/${DUPES}/runs`] = { data: [row(a, DUPES), row({ ...runRec(DUPES, "Duplicate vendor bills", 9010, 58, dupesRun().slice(1, 3).map((r, i) => i ? { ...r, answer: false, head: "no - a reissued invoice", why: "a reissued invoice" } : { ...r, rows: 1, head: "1 row" }), ago(10175)) }, DUPES)] };
  state[`/api/reports/${PAYROLL}/runs`] = { data: [row(b, PAYROLL)] };
  for (const r of [...state[`/api/reports/${DUPES}/runs`].data, ...state[`/api/reports/${PAYROLL}/runs`].data]) state[`/api/reports/runs/${r.runId}`] = r;
  // the run task the clean run made, with its steps on the card where a message would be
  const detail = (state["/api/tasks/detail"] ||= {});
  detail[DUPES_TASK] = {
    task: { TaskId: DUPES_TASK, Title: `Duplicate vendor bills - ${a.at.slice(0, 16)}`, Summary: "WORKFLOW RUN: Duplicate vendor bills - started by its schedule.\n4 steps, run by code; a model only where a step says AI.",
      Kind: "general", Status: "done", Priority: "normal", Assignee: null, Source: "workflow", SourceRef: `workflow:${DUPES}`, Tags: "workflow-trigger:schedule",
      CreatedBy: "schedule", CreatedAt: a.at, UpdatedAt: a.at, ClosedAt: a.at, Checklist: null, ChecklistMd: "", Playbook: null },
    ref: `TQ-00${DUPES_TASK}`, messages: [], checklist: [], attachments: [], artifacts: [], routes: [], runs: [], audit: [], reviews: [], session: null, transcript: null,
    comments: [`Workflow run (schedule): 4 steps, run by code - a model only where a step asks for one. No triage.`,
      ...a.steps.filter((r) => r.status !== "repaired").map((r, i) => `Step ${i + 1}/4 ${r.label}: ${r.head}`), a.summary].map((Body, i) => ({ CommentId: 6100 + i, TaskId: DUPES_TASK, Actor: "workflow", ActorType: "agent", Body, CreatedAt: a.at })),
    workflow: { source_id: DUPES, title: "Duplicate vendor bills", trigger: "schedule", schedule: "Mondays 07:00", started_by: "its schedule", runs_on: "", steps: a.steps, run_id: a.run_id, failed: false, summary: a.summary, repairs: a.repairs },
  };
  // ...and the run that failed: its task stays open, with the failed step on the card and Fix with AI one press away
  detail[63] = {
    ...detail[DUPES_TASK],
    task: { ...detail[DUPES_TASK].task, TaskId: 63, Title: `Payroll export to the share - ${b.at.slice(0, 16)}`, Status: "open", ClosedAt: null, CreatedAt: b.at, UpdatedAt: b.at,
      SourceRef: `workflow:${PAYROLL}`, Summary: "WORKFLOW RUN: Payroll export to the share - started by its schedule.\n3 steps, run by code; a model only where a step says AI." },
    ref: "TQ-0063",
    comments: ["Workflow run (schedule): 3 steps, run by code - a model only where a step asks for one. No triage.",
      `Step 1/3 Read the payroll export: failed: ${b.steps[0].error}`, b.summary].map((Body, i) => ({ CommentId: 6200 + i, TaskId: 63, Actor: "workflow", ActorType: "agent", Body, CreatedAt: b.at })),
    workflow: { source_id: PAYROLL, title: "Payroll export to the share", trigger: "schedule", schedule: "Fridays 06:00", started_by: "its schedule", runs_on: "", steps: b.steps, run_id: b.run_id, failed: true, summary: b.summary, repairs: [] },
  };
}

// Test this step, as the demo answers it: a read returns the recorded rows, the AI its recorded answer, anything that writes is dry
export function demoStepTest(body) {
  const step = body?.flow?.[body?.index] || {}, i = body?.index ?? 0;
  const base = { id: step.id, label: step.label || step.id, kind: step.kind, ms: 0 };
  const recorded = (dupesRun().find((r) => r.label === step.label) || null);
  if (step.kind === "source" && ["smb_write", "smb_move", "sftp_put", "sftp_move", "intacct_create", "intacct_update", "quickbooks_bill"].includes(step.type))
    return { ...base, status: "dry", head: `would run ${step.type}`, body: JSON.stringify({ type: step.type, path: step.path }, null, 1) };
  if (step.kind === "source") return /payroll_export/.test(step.query || "")
    ? { ...base, ms: 300, status: "failed", head: "failed", error: payrollRun()[0].error }
    : { ...base, ms: 790, status: "ok", head: "2 rows", rows: 2, body: ROWS };
  if (step.kind === "ai") return recorded ? { ...recorded, ms: 1180 } : { ...base, ms: 1100, status: "ok", answer: true, why: "the data says so", head: "yes - the data says so" };
  if (step.kind === "task") return { ...base, status: "dry", head: `would open a task '${String(step.title || "").replace("{{s1.rows}}", "2")}'`, body: step.summary || "" };
  if (step.kind === "draft") return { ...base, status: "dry", head: `would draft for ${step.to}`, body: step.about || "" };
  return { ...base, status: "dry", head: "would hand the run to the agent with this brief", body: `WORKFLOW RUN: (step ${i + 1})\nOBJECTIVE: ${step.prompt || ""}` };
}

// Take it back, in the demo: the steps before the repair come back, until the page reloads
export function demoUndo(state, sid) {
  const run = state["/api/reports/last-runs"]?.data?.[sid], rp = (run?.repairs || []).find((x) => !x.undone);
  if (!rp) { const e = new Error("there is no repair on that run to undo"); e.response = { status: 409, data: { detail: e.message } }; throw e; }
  const src = state["/api/sources"].data.find((x) => x.SourceId === Number(sid)), cfg = JSON.parse(src.ConfigJson);
  cfg.flow = cfg.flow.map((x) => (x.id === rp.step ? { ...x, query: rp.diff[0].keys[0].was } : x));
  src.ConfigJson = JSON.stringify(cfg); rp.undone = true;
  for (const r of state[`/api/reports/${sid}/runs`]?.data || []) if (r.runId === run.run_id) r.repairs = run.repairs;
  return { flow: cfg.flow, repairs: run.repairs };
}

export function demoRepair(state, sid) {
  if (Number(sid) !== PAYROLL) return { error: "That run did not fail - there is nothing to fix." };
  const src = state["/api/sources"].data.find((s) => s.SourceId === PAYROLL);
  const flow = JSON.parse(src.ConfigJson).flow;
  return { explain: "The table is payroll_exports (plural), and its period column holds YYYY-MM, so the query reads this month's period.",
    flow: flow.map((s) => s.id === "s1" ? { ...s, query: "SELECT employee_id, period, gross FROM payroll_exports WHERE period = LEFT('{{run.date}}', 7)" } : s),
    diff: [{ id: "s1", label: "Read the payroll export", change: "changed", keys: [{ key: "query" }] }], looked_at: [{ type: "mssql" }] };
}

// a workflow saved in the demo lives until the page reloads, like every other change a visitor makes
export function demoSaveSource(state, body) {
  const rows = (state["/api/sources"] ||= { data: [] }).data;
  const was = rows.find((s) => s.SourceId === body?.SourceId);
  if (was) { Object.assign(was, Object.fromEntries(Object.entries(body).filter(([, v]) => v != null))); return { sourceId: was.SourceId }; }
  const sid = Math.max(950, ...rows.map((s) => s.SourceId)) + 1;
  rows.push({ SourceId: sid, Owner: "owner", Active: 1, LastPolledAt: null, ...body });
  return { sourceId: sid };
}

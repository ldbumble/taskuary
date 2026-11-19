// A workflow has its own page (the owner, 2026-10-15: "there are a lot of buttons in weird places in workflows").
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
// the schedule helpers are plain functions; import them without React by slicing them out of the module
const src = read("WorkflowEditor.jsx");
const helpers = src.slice(src.indexOf("const DAYS"), src.indexOf("const Field"));
const { scheduleOf, withSchedule } = new Function(`${helpers.replace(/export /g, "")}; return { scheduleOf, withSchedule };`)();

test("every Monday at 8 is a weekly cron, and reads back as Monday - never daily", () => {
  const c = withSchedule({ title: "x", daily_at: "08:00" }, { mode: "weekly", at: "08:00", days: [1] });
  assert.deepEqual(c, { title: "x", cron: "0 8 * * 1" });
  assert.deepEqual(scheduleOf(c), { mode: "weekly", at: "08:00", days: [1] });
});

// WHEN IT RUNS is the server's to say (reports.schedule_words; tests/test_workflow_one_road.py holds its words): the editor, the Reports list
// and the report's Came from draw what it says - "every day at 08:00" here, "daily 08:00" on the task, "daily at 08:00" in the list was one routine
test("a workflow a mail starts says so, and every page surface says the clock in the server's words", () => {
  assert.ok(src.includes('set("on_mail"') && src.includes("Start when a mail like this arrives"));
  assert.match(src, /useScheduleWords\(withSchedule\(\{ on_mail: cfg\.on_mail \}, sched\)\)/);
  for (const f of ["WorkflowEditor.jsx", "ReportsView.jsx", "reportWords.js", "assistantCards.jsx"]) {
    const s = read(f);
    assert.doesNotMatch(s, /scheduleWords|runsWords|cronText|reportSchedule|startupText|`daily \$\{|every day at/, f);
  }
  assert.match(read("ReportsView.jsx"), /Runs \{source\.ScheduleWords\}/);
  assert.match(read("assistantCards.jsx"), /runs: row\?\.ScheduleWords/);
});

test("each schedule is one key, and the others are cleared", () => {
  assert.deepEqual(withSchedule({ cron: "0 8 * * 1" }, { mode: "daily", at: "07:30" }), { daily_at: "07:30" });
  assert.deepEqual(withSchedule({ daily_at: "07:30" }, { mode: "monthly", at: "09:00", day: 1 }), { cron: "0 9 1 * *" });
  assert.deepEqual(withSchedule({ daily_at: "07:30" }, { mode: "every", minutes: "45" }), { every_minutes: 45 });
  assert.deepEqual(withSchedule({ daily_at: "07:30", every_minutes: 5 }, { mode: "manual" }), {});
  assert.deepEqual(scheduleOf({ cron: "0 7 * * 1-5" }), { mode: "weekly", at: "07:00", days: [1, 2, 3, 4, 5] });
  assert.deepEqual(scheduleOf({ cron: "*/5 * * * *" }), { mode: "cron", cron: "*/5 * * * *" });
});

test("the page carries Run now for an unsaved workflow, and every field the run reads", () => {
  for (const want of ['"Save & run now"', '"Run now"', '"ask_first"', '"done_when"', '"uses"', '"browser"', "api.post(`/api/reports/${sid}/rerun`)"])
    assert.ok(src.includes(want), want);
});

test("Reports opens an agent workflow on its own page, with one way in to a new one", () => {
  const view = read("ReportsView.jsx");
  assert.match(view, /agentWorkflow\s*\n?\s*\? <WorkflowEditor/);
  assert.match(view, /label: "\+ New routine"/);
  assert.doesNotMatch(view, /label: "\+ AI agent"/);
  assert.doesNotMatch(view, /label: "\+ Monthly invoices"/);
  assert.match(view, /Monthly Zoho invoices have a form of their own/);
});

test("Reports offers New report and New workflow together, whichever list is open", () => {
  const view = read("ReportsView.jsx");
  assert.match(view, /\{ key: "new-report", label: "\+ New report" \}, \{ key: "new-dashboard", label: DASH\.new \}, \{ key: "new-agent", label: "\+ New routine" \},\s*\{ key: NEW_PB, label: "\+ New playbook" \}\]/);
  assert.doesNotMatch(view, /section === "workflows" \? \{ key: "new-agent"/);
  assert.ok(view.includes(">New report</Button>") && view.includes(">New routine</Button>"));
});

// B3 (the 2026-10-21 UI audit): the report editor's free "daily at HH:MM" box saved "7am", which the scheduler cannot read
test("a report's schedule is the workflow editor's picker, never a free time box", () => {
  const view = read("ReportsView.jsx");
  assert.ok(src.includes("export const SchedulePicker"), "the picker is one component");
  assert.ok(/<SchedulePicker sched=\{sched\}/.test(src) && /<SchedulePicker sched=\{sched\}/.test(view), "both editors draw it");
  assert.ok(!view.includes('label="daily at HH:MM"') && !view.includes('label="every N minutes"'), "no free box for the time");
  // every choice it offers comes back out as a key the scheduler reads (tests/test_report_schedule_saved.py reads the same shapes)
  assert.deepEqual(withSchedule({}, { mode: "daily", at: "07:00" }), { daily_at: "07:00" });
  assert.deepEqual(withSchedule({}, { mode: "weekly", at: "08:00", days: [3, 1] }), { cron: "0 8 * * 1,3" });
  assert.deepEqual(withSchedule({}, { mode: "monthly", at: "09:30", day: 1 }), { cron: "30 9 1 * *" });
});

// the audit (2026-11-13): the schedule's "at" box was 120px - an en-US "07:00 AM" and its clock icon showed "07:00 A" cut off, on every
// report, dashboard and routine that runs daily
test("the schedule's time box is wide enough for a 12-hour clock and its icon", () => {
  const w = +src.match(/type="time" label="at"[^]*?sx=\{\{ width: (\d+)/)[1];
  assert.ok(w >= 140, `at is ${w}px`);
});

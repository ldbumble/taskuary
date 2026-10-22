// A workflow has its own page (the owner, 2026-10-15: "there are a lot of buttons in weird places in workflows").
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
// the schedule helpers are plain functions; import them without React by slicing them out of the module
const src = read("WorkflowEditor.jsx");
const helpers = src.slice(src.indexOf("const DAYS"), src.indexOf("const Field"));
const { scheduleOf, withSchedule, scheduleWords } = new Function(`${helpers.replace(/export /g, "")}; return { scheduleOf, withSchedule, scheduleWords };`)();

test("every Monday at 8 is a weekly cron, and reads back as Monday - never daily", () => {
  const c = withSchedule({ title: "x", daily_at: "08:00" }, { mode: "weekly", at: "08:00", days: [1] });
  assert.deepEqual(c, { title: "x", cron: "0 8 * * 1" });
  assert.deepEqual(scheduleOf(c), { mode: "weekly", at: "08:00", days: [1] });
  assert.equal(scheduleWords(scheduleOf(c)), "Mon at 08:00");
});

test("a workflow a mail starts says so, and the page asks which mail in words", () => {
  const { runsWords } = new Function(`${helpers.replace(/export /g, "")}; return { runsWords };`)();
  assert.equal(runsWords({ mode: "manual" }, { on_mail: "a vendor sends an invoice" }), "when a mail like the one described arrives");
  assert.equal(runsWords({ mode: "weekly", at: "08:00", days: [1] }, { on_mail: "x" }), "Mon at 08:00, and when a mail like the one described arrives");
  assert.equal(runsWords({ mode: "manual" }, {}), "only when you press Run now");
  assert.ok(src.includes('set("on_mail"') && src.includes("Start when a mail like this arrives"));
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
  assert.match(view, /label: "\+ New workflow"/);
  assert.doesNotMatch(view, /label: "\+ AI agent"/);
  assert.doesNotMatch(view, /label: "\+ Monthly invoices"/);
  assert.match(view, /Monthly Zoho invoices have a form of their own/);
});

test("Reports offers New report and New workflow together, whichever list is open", () => {
  const view = read("ReportsView.jsx");
  assert.match(view, /\{ key: "new-report", label: "\+ New report" \}, \{ key: "new-agent", label: "\+ New workflow" \}, \{ key: NEW_PB, label: "\+ New playbook" \}\]/);
  assert.doesNotMatch(view, /section === "workflows" \? \{ key: "new-agent"/);
  assert.ok(view.includes(">New report</Button>") && view.includes(">New workflow</Button>"));
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

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
  assert.match(view, /\{ key: "new-report", label: "\+ New report" \}, \{ key: "new-agent", label: "\+ New workflow" \}\]/);
  assert.doesNotMatch(view, /section === "workflows" \? \{ key: "new-agent"/);
  assert.ok(view.includes('>{tx("New report")}</Button>') && view.includes('>{tx("New workflow")}</Button>'));
});

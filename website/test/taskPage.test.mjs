import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

// TaskPage is the Tasks tab's task view, extracted so the assistant canvas shows the very same view (the canvas
// redesign, 2026-09-29): the list owns selection and what comes next, the view owns one task.
test("the Tasks tab draws the task through TaskPage, and the list holds no task state of its own", () => {
  const list = src("TasksView.jsx"), page = src("TaskPage.jsx");
  assert.match(list, /import TaskPage from "\.\/TaskPage\.jsx"/);
  assert.match(list, /<TaskPage taskId=\{selected\}/);
  for (const own of ["const [detail, setDetail]", "const [term, setTerm]", "const loadDetail", "WorkflowHeading number="])
    assert.ok(!list.includes(own) && page.includes(own), own);
});

test("the view takes the list's part as props - it never loads the task list itself", () => {
  const page = src("TaskPage.jsx");
  assert.match(page, /export default function TaskPage\(\{ taskId: selected, listRow = null, onListChanged, onSelect, onClose, onFinish, onReminded,/);
  assert.doesNotMatch(page, /api\.get\("\/api\/tasks", /);
  assert.match(page, /data-tq-task-page=\{selected \|\| ""\}/);
  assert.match(page, /height: canvas \? "auto" : "calc\(100vh - 118px\)"/);
});

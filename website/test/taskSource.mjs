// The Tasks tab's source: the list (TasksView.jsx) and the task view it shows beside it (TaskPage.jsx), which were one
// file until the canvas redesign (2026-09-29) extracted the view so the assistant canvas can show it too. The tests
// that read the tab's source read both - the page is the same page.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
export const taskSource = () => `${read("TasksView.jsx")}\n${read("TaskPage.jsx")}`;

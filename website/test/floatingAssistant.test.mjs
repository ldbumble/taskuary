import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the assistant header stays small and opens app-level walkthrough and add choices", () => {
  const source = read("FloatingAssistant.jsx");
  const block = source.match(/const STARTERS = \[([\s\S]*?)\n\];/)?.[1] || "";
  const labels = [...block.matchAll(/^\s*\["([^"]+)"/gm)].map((m) => m[1]);
  assert.deepStrictEqual(labels, ["Walk through", "Add", "Set up report"]);
  assert.doesNotMatch(source, /\["End of day"/);
  assert.match(source, /const WALKTHROUGHS =/);
  assert.match(source, /\["Inbox"/);
  assert.match(source, /\["Tasks"/);
  assert.match(source, /\["Agent work"/);
  assert.match(source, /\["Review"/);
  assert.match(source, />Task<\/Button>/);
  assert.match(source, />Report<\/Button>/);
  assert.match(source, />Connection<\/Button>/);
});

test("add shortcuts open the native new-task and new-report surfaces", () => {
  const shell = read("FloatingAssistant.jsx");
  assert.match(shell, /window\.location\.hash = "new-task"/);
  assert.match(shell, /window\.location\.hash = "report=new"/);
  assert.match(read("TasksView.jsx"), /window\.location\.hash === "#new-task"/);
  assert.match(read("ReportsView.jsx"), /value === "new"/);
});

test("the floating guide's AI choices render above the guide", () => {
  const source = read("GeneralWorkspace.jsx");
  const z = Number(source.match(/MenuProps=\{\{ sx: \{ zIndex: (\d+) \}/)?.[1] || 0);
  assert.ok(z > 1450, `AI menu z-index ${z} must clear the guide's 1450 layer`);
});

test("Taskuary has compact and Timeline-stage expanded modes without moving the app shell", () => {
  const source = read("FloatingAssistant.jsx");
  assert.match(source, />Taskuary<\/Typography>/);
  assert.doesNotMatch(source, />Taskuary guide<\/Typography>/);
  assert.match(source, /OpenInFullIcon/);
  assert.match(source, /CloseFullscreenIcon/);
  assert.match(source, /data-tq-timeline-stage/);
  assert.match(source, /getBoundingClientRect/);
  assert.match(source, /dockExpanded=\{expanded\}/);
  const page = read("TaskHubPage.jsx");
  assert.doesNotMatch(page, /assistantExpanded/);
  assert.doesNotMatch(page, /onExpandedChange/);
  assert.match(read("FeedView.jsx"), /data-tq-timeline-stage/);
});

test("assistant commentary and owner actions are separate surfaces", () => {
  const source = read("GeneralWorkspace.jsx");
  assert.match(source, /export function DockActions/);
  assert.match(source, /"Approve & send"/);
  assert.match(source, /"Redraft"/);
  assert.match(source, />Dismiss<\/Button>/);
  assert.match(source, /\/api\/reviews\/\$\{r\.ReviewId\}\/decide/);
  assert.match(source, /\/api\/reviews\/\$\{r\.ReviewId\}\/draft/);
  assert.match(source, /<div className="tq-aui-role">Taskuary<\/div>/);
  assert.match(source, /newChatBusy \? "Starting…" : "New chat"/);
  assert.match(source, /onDockNewChat/);
  assert.doesNotMatch(source, /window\.confirm/);
  assert.match(source, />Keep this chat<\/Button>/);
  assert.match(source, />Start new chat<\/Button>/);
  assert.match(source, /aria-label="Confirm new chat"/);
  const shell = read("FloatingAssistant.jsx");
  assert.match(shell, /<DockActions messages=\{\[\]\}/);
  assert.match(shell, /api\.post\("\/api\/assistant\/dock\/new"\)/);
});

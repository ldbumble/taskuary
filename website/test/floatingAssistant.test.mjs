import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the guide keeps the three walkthrough shortcuts plus the end-of-day brief", () => {
  const source = read("FloatingAssistant.jsx");
  const block = source.match(/const STARTERS = \[([\s\S]*?)\n\];/)?.[1] || "";
  const labels = [...block.matchAll(/^\s*\["([^"]+)"/gm)].map((m) => m[1]);
  assert.deepStrictEqual(labels, ["Walk through it all", "Important now", "Outstanding tasks", "End of day"]);
});

test("the floating guide's AI choices render above the guide", () => {
  const source = read("GeneralWorkspace.jsx");
  const z = Number(source.match(/MenuProps=\{\{ sx: \{ zIndex: (\d+) \}/)?.[1] || 0);
  assert.ok(z > 1450, `AI menu z-index ${z} must clear the guide's 1450 layer`);
});

test("Taskuary has a compact and expanded right-side workspace without calling itself a guide", () => {
  const source = read("FloatingAssistant.jsx");
  assert.match(source, />Taskuary<\/Typography>/);
  assert.doesNotMatch(source, />Taskuary guide<\/Typography>/);
  assert.match(source, /OpenInFullIcon/);
  assert.match(source, /CloseFullscreenIcon/);
  assert.match(source, /min\(760px, 58vw\)/);
  assert.match(source, /dockExpanded=\{expanded\}/);
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
  const shell = read("FloatingAssistant.jsx");
  assert.match(shell, /<DockActions messages=\{\[\]\}/);
  assert.match(shell, /api\.post\("\/api\/assistant\/dock\/new"\)/);
});

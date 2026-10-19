import { taskSource } from "./taskSource.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(f, import.meta.url)), "utf8");
const workspace = read("../src/GeneralWorkspace.jsx");
const tasks = taskSource();

// A general agent is a chat, the way a coding agent is a terminal. The strip above it used to
// switch the body between the conversation, a fake terminal of the same conversation (which
// staircased every multi-line reply), a browser button and a numbers panel - four things to
// choose between before reading what the agent said (the owner, 2026-09-22).
test("the general workspace has no view switcher - the conversation is the only body", () => {
  const strip = workspace.slice(workspace.indexOf("const tools = (<>"), workspace.indexOf("{dock && <Box"));
  for (const word of [">Terminal<", ">Numbers<", ">Assistant<", '"Browser"']) assert.doesNotMatch(strip, new RegExp(word));
  assert.match(strip, /Full screen/, "the whole-window toggle stays, like a coding agent's");
  assert.doesNotMatch(workspace, /paneFor|taskuary_general_view|SemanticPanel|TerminalPane/);
});

test("the chat renders with or without a live session - a session only adds the browser split", () => {
  // one tree either way: the pane takes a null sid, so a session that arrives mid-turn never remounts the thread (2026-10-02)
  assert.match(workspace, /<SessionPane sid=\{session\?\.sid \|\| null\}[^>]*expectBrowser=\{wantsBrowser\(task\)\}>\{thread\}<\/SessionPane>/);
});

test("the chat takes the room on the task page, the way a live session does", () => {
  const at = tasks.indexOf('{workspaceMode === "general" && (liveSession');
  const mount = tasks.slice(at, tasks.indexOf('workspaceMode === "wrapping"', at));
  assert.match(mount, /flex: "1 1 0"/);
  // ...on the canvas, all of the view under the title and its heading (the owner, 2026-10-18: "see more of the agent canvas")
  assert.match(mount, /minHeight: canvas \? "max\(240px, calc\(100cqh - 78px\)\)" : \{ xs: 360, md: 420 \}/);
});

// THE AGENT'S CHAT OPENS PUSHED UP on the canvas: the folded Task strip scrolls above, and back down when another step opens
test("on the canvas the agent step scrolls the Task strip away, and another step scrolls it back", () => {
  assert.match(tasks, /const agentUp = !!canvas && stage === "agent" && workspaceMode === "general" && !liveSession;/);
  assert.match(tasks, /if \(!agentUp\) \{ if \(canvas && stepsBox\.current\) stepsBox\.current\.scrollTop = 0; return undefined; \}/);
  assert.match(tasks, /<Box ref=\{stepsBox\} sx=\{\{ px: liveSession/);
  assert.match(tasks, /\{!sessionView && !\(canvas && stage === "agent"\) && <Box data-tq-triage-facts=""/);
});

// END SESSION ON A GENERAL AGENT (the owner, 2026-10-13): its chat stayed drawn under Agent work with Close out folded below,
// where a coding session's terminal goes away. Drawn while live, or when the owner opens Agent work - otherwise the page's
// own focus (focusStage: a draft ready is Close out) decides.
test("an ended general session's chat gives the page back to the stage that is focused", () => {
  const src = read("../src/TaskPage.jsx");
  assert.match(src, /\{workspaceMode === "general" && \(liveSession \|\| stage === "agent"\) \? \(/);
});

// THE CHAT'S STRIP RIDES IN THE STEP'S HEADING ON THE CANVAS: "Agent work" on one row and the agent's name, brain and Full screen on
// a second took two lines off the answer (the owner, 2026-10-18: "make the agent space take up more space")
test("on the canvas the chat's brain and Full screen sit in the agent step's heading, and come home in full screen", () => {
  assert.match(tasks, /tools=\{inRow && workspaceMode === "general" && \(liveSession \|\| stage === "agent"\)\s*\? <Box ref=\{setChatTools\}/);
  assert.match(tasks, /toolsAt=\{canvas \? chatTools : null\}/);
  assert.match(workspace, /\{!dock && toolsAt && !full && createPortal\(tools, toolsAt\)\}/);
  assert.match(workspace, /\{!dock && !\(toolsAt && !full\) && <Box sx=\{\{ minHeight: 39,/);
});

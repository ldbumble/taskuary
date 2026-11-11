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
  assert.doesNotMatch(workspace, /paneFor|taskuary_general_view|SemanticPanel/);
  // ...a coding CLI's screen is drawn only as the card while it asks - never a body to switch to
  assert.equal((workspace.match(/<TerminalPane /g) || []).length, 1);
  assert.match(workspace, /\{screenAsks && <div className="tq-cc-screen" data-tq-chat-screen=""/);
});

test("the chat renders with or without a live session - a session only adds the browser split", () => {
  // one tree either way: the pane takes a null sid, so a session that arrives mid-turn never remounts the thread (2026-10-02)
  assert.match(workspace, /<SessionPane sid=\{\(!noTools && session\?\.sid\) \|\| null\}[^>]*>\{thread\}<\/SessionPane>/);
});

test("the chat takes the room on the task page, the way a live session does", () => {
  const at = tasks.indexOf('{workspaceMode === "general" && (liveSession');
  const mount = tasks.slice(at, tasks.indexOf('workspaceMode === "wrapping"', at));
  assert.match(mount, /flex: "1 1 0"/);
  // ...on the canvas, all of the view under the title and its heading (the owner, 2026-10-18: "see more of the agent canvas")
  // ...less what Continue's box takes while it stands open over the chat (2026-11-09): with the whole view as its floor the chat's own box left the screen
  assert.match(mount, /minHeight: canvas \? "max\(240px, calc\(100cqh - 113px\)\)" : \{ xs: 360, md: 420 \}/);
});

// THE AGENT'S CHAT OPENS PUSHED UP on the canvas: the folded Task strip scrolls above, and back down when another step opens
test("on the canvas the agent step scrolls the Task strip away, and another step scrolls it back", () => {
  assert.match(tasks, /const agentUp = !!canvas && shows\("agent"\) && workspaceMode === "general" && !liveSession;/);
  assert.match(tasks, /if \(!agentUp\) \{ if \(canvas && stepsBox\.current\) stepsBox\.current\.scrollTop = 0; return undefined; \}/);
  // ...the stacked page's one scroller; on the desk each of the three sections scrolls on its own (2026-10-27)
  assert.match(tasks, /<Box ref=\{stepsBox\} sx=\{twoUp \? \{ flex: 1, minHeight: 0, minWidth: 0, display: "flex", flexDirection: "row"[^\n]*\n\s+: \{ px: liveSession/);
});

// END SESSION ON A GENERAL AGENT (the owner, 2026-10-13): its chat stayed drawn under Agent work with Close out folded below,
// where a coding session's terminal goes away. Drawn while live, or when the owner opens Agent work - otherwise the page's
// own focus (focusStage: a draft ready is Close out) decides.
test("an ended general session's chat gives the page back to the stage that is focused", () => {
  const src = read("../src/TaskPage.jsx");
  assert.match(src, /\{workspaceMode === "general" && \(liveSession \|\| shows\("agent"\)\) \? \(/);
  // ...a finished one's chat is the rest of its Result, behind the Result heading while the Result rests on its summary - unless it asks (2026-10-27)
  // ...or that is at work again: a turn under way shows (its band, its thinking line, or its "Working on this…")
  // ...and a failed run rests on its reason and fix the same way (2026-10-28)
  assert.match(src, /\.\.\.\(!chatPane && \(resultRest \|\| \(failedRun && !resultOpen\)\) \? \{ "&:not\(:has\(\[data-tq-asking\], \[data-tq-agent-notice\], \.tq-aui-band, \.tq-aui-thinking, \.tq-aui-thread \[data-tq-working\], \[data-tq-waits\], \[data-tq-on-you\]\)\)": \{ display: "none" \} \} : \{\}\)/);
  // ...or that holds what waits on the owner: a draft card or an On you step in its summary (Task 4.2)
});

// THE CHAT'S STRIP RIDES IN THE STEP'S HEADING ON THE CANVAS: "Agent work" on one row and the agent's name, brain and Full screen on
// a second took two lines off the answer (the owner, 2026-10-18: "make the agent space take up more space")
test("on the canvas the chat's brain and Full screen sit in the agent step's heading, and come home in full screen", () => {
  // ...only while its session is live: a failed or closed agent's heading carries no picker, "provider default" or Full screen (the owner,
  // 2026-10-25) - GeneralWorkspace draws none of them anywhere then (noTools)
  assert.match(tasks, /tools=\{inRow && workspaceMode === "general" && liveSession\s*\? <Box ref=\{setChatTools\}/);
  assert.match(tasks, /noTools=\{!liveSession\}/);
  assert.match(tasks, /toolsAt=\{canvas \? chatTools : null\}/);
  assert.match(workspace, /\{!dock && !noTools && !chat && toolsAt && !full && <>\{createPortal\(tools, toolsAt\)\}<\/>\}/);
  assert.match(workspace, /\{!dock && !noTools && !chat && !\(toolsAt && !full\) && <Box sx=\{\{ minHeight: 39,/);
});

test("the chat box says the agent, never \"the assistant\" over an analyst (email walk 2026-10-29; the owner, 2026-11-06)", () => {
  assert.match(workspace, /placeholder=\{askWords \|\| placeholder \|\| \(dock \? "Tell Taskuary what to do next…" : MESSAGE\)\}/, "one prompt wording (audit 2026-11-05)");
  assert.doesNotMatch(workspace, /Tell the assistant what to do next/);
});

// A SEND THAT FAILED STAYS ON SCREEN (the owner, 2026-11-02: "the text goes no where"): the read after a failed turn tells the page the
// session is down, but never resets the thread - the server's copy has neither the reason nor words the agent never took
test("a failed send keeps the owner's words and the reason in the chat", () => {
  const failed = workspace.slice(workspace.indexOf("const failed = useCallback("), workspace.indexOf("const loaded = !!data"));
  // ...the server's copy handed to the thread only when it says the failure (general.with_failure): a poll's copy from before it, applied as the run
  // ended, wiped the turn's "⚠" and left his line under a head spinning for a minute (the overnight walk, 2026-11-11)
  assert.match(failed, /accept\(r\.data\); if \(r\.data\?\.messages\?\.at\(-1\)\?\.failed\) setRevision\(\(k\) => k \+ 1\)/);
  assert.match(workspace, /onEnded=\{failed\}/);
  // ...and the adapter still says the reason under the message on both roads: an error event and a refused request
  assert.match(workspace, /onEnded\?\.\(\);\s*\n\s*yield \{ content: content\(`⚠ \$\{event\.error/);
  assert.match(workspace, /onEnded\?\.\(\);\s*\n\s*yield \{ content: content\(`⚠ \$\{e\?\.message/);
});

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
  assert.match(workspace, /<SessionPane sid=\{\(!noTools && session\?\.sid\) \|\| \(coding && needNow && cli\?\.sid\) \|\| null\}[^>]*>\{thread\}<\/SessionPane>/);
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
  assert.match(src, /\.\.\.\(!chatPane && \(resultRest \|\| \(failedRun && !resultOpen\)\) \? \{ "&:not\(:has\(\[data-tq-asking\], \[data-tq-agent-notice\], \.tq-aui-thinking, \.tq-aui-thread \[data-tq-working\], \[data-tq-waits\], \[data-tq-on-you\]\)\)": \{ display: "none" \} \} : \{\}\)/);
  // ...or that holds what waits on the owner: a draft card or an On you step in its summary (Task 4.2)
});




// A QUESTION IS SAID ONCE (the audit, 2026-11-15: the agent's words ended on its question, and "For you to do: Tell me ..." said it again under them)
test("a turn's open question is not said again as what is left to him", async () => {
  const fs = await import("node:fs");
  const src = read("../src/GeneralWorkspace.jsx");
  assert.match(src, /const onYou = t\.on_you && !live && sum \? turnOnYou\(sum\) : "";/);   // ...each turn's own, settled by the list (design round 5)
  assert.match(src, /owes = onYouTurn\(items, \{ askAt, lettersAt, landAt: landIn \}\)/);
});

// The chat's stylesheet styles only what the chat draws: a rule for a class no element carries is a second, drifting copy of a look
// (several such rules still carried the 9px tracked capitals the chat dropped). A class is carried when a source file names it, or
// builds it from a named prefix (`tq-aui-tool-${status}`).
test("every class the chat's stylesheet styles is one some component puts on an element", async () => {
  const { readdirSync } = await import("node:fs");
  const dir = fileURLToPath(new URL("../src/", import.meta.url));
  const src = readdirSync(dir, { recursive: true }).filter((f) => /\.(jsx?|mjs)$/.test(f)).map((f) => readFileSync(dir + f, "utf8")).join("\n");
  const named = new Set(src.match(/tq-[a-z0-9-]*[a-z0-9]/g));
  const prefixes = [...src.matchAll(/(tq-[a-z0-9-]*-)\$\{/g)].map((m) => m[1]);
  const css = read("../src/generalWorkspace.css").replace(/\/\*[\s\S]*?\*\//g, "");
  const styled = new Set([...css.matchAll(/\.(tq-[a-z0-9-]*[a-z0-9])/g)].map((m) => m[1]));
  const unworn = [...styled].filter((c) => !named.has(c) && !prefixes.some((p) => c.startsWith(p)));
  assert.deepEqual(unworn, []);
});

// "For you to do: Send any message on this task when you want the portal tried again" (the 2026-11-18 walks): a turn whose summary says it is
// worth another go draws one Try again under it, the line it sends his - never a sentence asking him to type something
test("a turn worth another try ends on a Try again button that sends his line", () => {
  const src = read("../src/GeneralWorkspace.jsx");
  assert.match(src, /owes && !live && sum\?\.retry && !!again && <div style=\{\{ marginTop: 8 \}\}><button type="button" className="tq-chip primary" data-tq-turn-retry="" onClick=\{again\}>\{btn\("try_again"\)\}<\/button>/);
  assert.match(src, /const again = useCallback\(\(\) => sendLine\(TRY_AGAIN\), \[sendLine\]\);/);
});

// The API walk, 2026-11-18: a provider's outage left "⚠ ... 429" under every line and nothing to press - the newest failed turn carries Try again
test("the newest turn that failed carries the Try again button, an older one does not", () => {
  const src = read("../src/GeneralWorkspace.jsx");
  assert.match(src, /data-tq-turn-failed="">⚠ \{t\.fail\}\s*\{newest && !!again && <div style=\{\{ marginTop: 8 \}\}><button type="button" className="tq-chip primary" data-tq-turn-retry="" onClick=\{again\}>/);
  assert.match(src, /newest=\{!items\.slice\(i \+ 1\)\.some\(\(y\) => y\.kind === "turn"\)\}/);
});

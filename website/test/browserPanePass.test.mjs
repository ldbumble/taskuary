// The browser pane, watched live from a first turn to a closed browser (the 2026-10-02 pane pass). The arithmetic is
// in browserSplit.test.mjs; this pins where the components read it, since the JSX never loads under node --test.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8").replace(/\r\n/g, "\n");
const pane = src("BrowserPane.jsx"), term = src("TerminalView.jsx"), gw = src("GeneralWorkspace.jsx");

test("the first turn's session is taken from the stream's start, not its done", () => {
  assert.match(gw, /event\.type === "start"\) \{\n\s*onStarted\?\.\(event\.session\)/);
  assert.match(gw, /setData\(\(d\) => \(d && !d\.session \? \{ \.\.\.d, session: s \} : d\)\)/);
  // the thread sits inside the pane with or without a session: swapping the wrapper mid-turn remounts the stream
  // ...a session that is not live (`noTools`) has no sid there: its browser is not asked after (2026-10-26)
  assert.match(gw, /<SessionPane sid=\{\(!noTools && session\?\.sid\) \|\| null\}/);
  assert.doesNotMatch(gw, /\{session \? \(\s*<SessionPane/);
  assert.match(term, /if \(!sid\) return undefined;/);
});

test("a reopened task's address bar follows the url the server reports", () => {
  assert.match(pane, /useEffect\(\(\) => \{ if \(url0\) setUrl\(url0\); \}, \[url0\]\)/);
});

test("the socket connects only while the browser is open, and backs off", () => {
  assert.match(pane, /if \(!open\) \{ setLive\(false\); return undefined; \}/);
  assert.match(pane, /\}, \[sid, open\]\);/);
  assert.match(pane, /2000 \* 2 \*\* tries\+\+/);
  assert.match(term, /showsBrowser\(browser\.open, browser\.url\)/);
  assert.equal((term.match(/open=\{browser\.open\}/g) || []).length, 3, "the stack, the split and the peek all pass it");
});

test("the first frame of a connection sends the pane's shape, which a still-starting browser was refused (2026-11-04)", () => {
  assert.match(pane, /if \(!shaped\.current\) \{ shaped\.current = true; fitViewport\(true\); \}/);
  assert.match(pane, /ws\.onclose = \(\) => \{ setLive\(false\); shaped\.current = false;/);
});

test("your turn is never said over a pane with no frame drawn (2026-11-04)", () => {
  assert.match(pane, /\{!live \? "waiting for the page to draw — type once it shows" : handed\.current \? "your turn/);
});

test("the viewport is set only by the tab the owner is at", () => {
  assert.match(pane, /mayShape\(document\.hidden, document\.hasFocus\(\), claim\)/);
  // ...and a click on the page reshapes it only if the pane's shape moved - a claim re-sent under the owner's first click (2026-11-03)
  assert.match(pane, /onPointerDown=\{\(\) => fitViewport\(\)\}/);
});

test("the split never takes the chat below its minimum width", () => {
  assert.match(term, /splitRatio\(ratio, width\)/);
});

test("the top bar wraps on a phone instead of widening the page", () => {
  // one ~540px row at 390 set the layout width to 493: every screen zoomed out, the right-hand icons off the edge
  const hub = src("TaskHubPage.jsx"), nav = hub.slice(hub.indexOf('<Box id="tqTopNav"'), hub.indexOf('<Box id="tqTopNav"') + 300);
  assert.match(nav, /flexWrap: \{ xs: "wrap", md: "nowrap" \}/);
});

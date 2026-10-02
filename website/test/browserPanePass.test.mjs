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
  assert.match(gw, /<SessionPane sid=\{session\?\.sid \|\| null\}/);
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
  assert.match(term, /showsBrowser\(browser\.open, expectBrowser, seen\)/);
  assert.equal((term.match(/open=\{browser\.open\}/g) || []).length, 2, "the split and the peek both pass it");
});

test("the viewport is set only by the tab the owner is at", () => {
  assert.match(pane, /mayShape\(document\.hidden, document\.hasFocus\(\), claim\)/);
  assert.match(pane, /onPointerDown=\{\(\) => fitViewport\(true\)\}/);
});

test("the split never takes the chat below its minimum width", () => {
  assert.match(term, /splitRatio\(ratio, width\)/);
});

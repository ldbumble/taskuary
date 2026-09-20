import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { adoptPtyGeometry } from "../src/terminalSizing.js";

// The browser build of xterm parses and resizes without a DOM as long as open() is never called.
const { Terminal } = createRequire(import.meta.url)("@xterm/xterm");
const CRLF = String.fromCharCode(13, 10);
const scrolled = () => new Promise((done) => {
  const term = new Terminal({ rows: 32, cols: 110, scrollback: 1000, allowProposedApi: true });
  term.write(Array.from({ length: 50 }, (_, i) => `line ${i}`).join("\r\n"), () => done(term));
});

// ConPTY keeps its viewport top-anchored on a grow: the cursor stays on its row and the new rows
// are blank. xterm's default pulls scrollback back in and moves the cursor down - and the CLI's
// next absolute cursor move then lands mid-pane over lines it already drew (2026-09-18).
test("a ConPTY-backed pane keeps the cursor row when it grows", async () => {
  const term = await scrolled();
  adoptPtyGeometry(term, { type: "geom", rows: 32, cols: 110, owner: true, conpty: true });
  term.resize(110, 60);
  assert.equal(term.buffer.active.cursorY, 31);
  assert.equal(term.buffer.active.baseY, 18);
});

test("a posix pty pane still pulls its scrollback into a grown viewport", async () => {
  const term = await scrolled();
  adoptPtyGeometry(term, { type: "geom", rows: 32, cols: 110, owner: true, conpty: false });
  term.resize(110, 60);
  assert.equal(term.buffer.active.cursorY, 49);
  assert.equal(term.buffer.active.baseY, 0);
});

test("a geom frame from an older server leaves the terminal alone", async () => {
  const term = await scrolled();
  adoptPtyGeometry(term, { type: "geom", rows: 32, cols: 110, owner: true });
  term.resize(110, 60);
  assert.equal(term.buffer.active.cursorY, 49);
});

// ConPTY itself reflows wrapped lines on a width change only from Windows build 21376; xterm's
// reflow follows the build it is told about, so the two agree on old Windows 10 as well.
test("the Windows build rides into xterm's windowsPty option", async () => {
  const term = await scrolled();
  adoptPtyGeometry(term, { type: "geom", rows: 32, cols: 110, owner: true, conpty: true, build: 26200 });
  assert.deepEqual(term.options.windowsPty, { backend: "conpty", buildNumber: 26200 });
  adoptPtyGeometry(term, { type: "geom", rows: 32, cols: 110, owner: true, conpty: true, build: null });
  assert.deepEqual(term.options.windowsPty, { backend: "conpty" });
});

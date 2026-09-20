// One PTY, one geometry owner - the browser half.
//
// Several panes can watch one session at once (task page, Wall cell, Feed preview, assistant
// card) and each used to fit its own xterm to its OWN box and send that size to the shared PTY.
// The last one to speak won, and every other pane was then rendering a child that wraps at a
// width its emulator does not have: absolute cursor moves land on rows nobody wrote and the pane
// shows two frames at once (the owner, 2026-09-16, photographed on the Wall while the task page
// held the same session). The server picks one owner (Term.geom_owner) and says so in a `geom`
// frame; this is the client obeying it. The server side is tests/test_one_pty_one_geometry.py.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const term = fs.readFileSync(path.join(process.cwd(), "src", "TerminalView.jsx"), "utf8");

test("a pane that does not own the geometry renders at the PTY's size, not its box", () => {
  assert.match(term, /let ownsGeometry = true, ptySize = null;/);
  const at = term.indexOf("const fitSafely = () => {");
  assert.notEqual(at, -1, "fitSafely must exist");
  const fitFn = term.slice(at, at + 500);
  assert.ok(fitFn.includes("if (!ownsGeometry) {"),
    "fitSafely has to bail out before fit() for a non-owner");
  assert.ok(/term\.resize\(ptySize\.cols, ptySize\.rows\)/.test(fitFn),
    "a non-owner must match the PTY's geometry, or it wraps where the child did not");
  // and fit() must still be reachable for the owner - a bail-out that swallowed both is worse
  assert.ok(fitFn.includes("fit.fit();"), "the owner still fits its own box");
});

test("only the owner tells the PTY a size", () => {
  const at = term.indexOf("const sendSize = () => {");
  assert.notEqual(at, -1);
  assert.ok(term.slice(at, at + 420).includes("!ownsGeometry"),
    "sendSize must be gated on ownership, not only on readOnly");
});

test("the geom frame is handled, and taking ownership back re-sends the size", () => {
  const at = term.indexOf('else if (m.type === "geom")');
  assert.notEqual(at, -1, "the client must handle the server's geom frame");
  const handler = term.slice(at, at + 600);
  assert.ok(handler.includes('ownsGeometry = m.owner !== false;'),
    "absent or true means this pane owns it - an older server sends no geom at all");
  assert.ok(handler.includes("fitSafely();"), "the new geometry has to be applied at once");
  // The owning pane can close while this one is still open. The server frees the token, this
  // pane claims it on its next resize - but sentSize still holds the size it last sent, so
  // without clearing it the claim would be deduplicated away and the PTY never told.
  assert.ok(/sentSize = "";\s*sendSize\(\);/.test(handler),
    "regaining ownership must clear the dedupe and re-assert this pane's size");
});

test("a pane that comes back into view repaints from xterm's buffer", () => {
  // Hidden behind another tab the box is unusable and onResize returns early; on the way back the
  // canvas showed whatever xterm last painted - often nothing - until the next byte arrived (the
  // owner, 2026-09-18: "can't see anything ... especially when I click away and come back").
  assert.match(term, /let wasHidden = false;/);
  assert.match(term, /if \(!box \|\| !usableTerminalBox\(box\.width, box\.height\)\) \{ wasHidden = true; return; \}/);
  assert.match(term, /if \(wasHidden\) \{ wasHidden = false; term\.refresh\(0, Math\.max\(0, term\.rows - 1\)\); \}/);
  assert.match(term, /document\.addEventListener\("visibilitychange", onVisible\)/);
  assert.match(term, /document\.removeEventListener\("visibilitychange", onVisible\)/, "and it is taken down with the pane");
});

test("the pane's knobs clear the full-screen button, and the connection word rides in their row", () => {
  // SessionPane's full-screen button sits at right: 6 over the same corner; at right: 10 the knob
  // row ended under it and every pane read "Catppuccin Moch" (2026-09-18). The state word used to
  // float at right: 130 - the width of one particular knob row - and collided in narrow Wall cells.
  assert.match(term, /position: "absolute", top: 3, right: 36, zIndex: 2, display: "flex"/);
  assert.doesNotMatch(term, /right: 130/);
  const knobs = term.slice(term.indexOf("right: 36, zIndex: 2"), term.indexOf("A\u2212</Box>"));
  assert.match(knobs, /\{state !== "live" && \(/, "the connection word is the first thing in the knob row");
});

test("the knobs sit on the pane's background, and a narrow pane draws none", () => {
  // At 62% opacity with no backdrop the first row of the run printed straight through
  // "A\u2212 10 A+ Catppuccin Mocha"; on a phone and in the walk's agent card the row spanned the
  // whole pane and covered the first three rows (2026-09-20). Solid backdrop, faded knobs; and
  // under 520px the row is not drawn - the full-screen button is enough there.
  const knobs = term.slice(term.indexOf("!readOnly && !narrow &&"), term.indexOf("A\u2212</Box>"));
  assert.match(knobs, /bgcolor: THEMES\[themeName\]\.background/, "the backdrop is the pane's own colour");
  assert.match(knobs, /"& > \*": \{ opacity: 0\.62/, "only the knobs fade, never the backdrop");
  assert.match(term, /new ResizeObserver\(\(entries\) => setNarrow\(\(entries\[0\]\?\.contentRect\.width \|\| 0\) < 520\)\)/);
  assert.match(term, /<Box ref=\{root\} sx=\{\{ position: "relative"/, "the pane's own box is what is measured");
});

test("nothing touches xterm after the pane is disposed", () => {
  // A write's completion callback ran scrollToBottom on a terminal whose renderer dispose() had
  // already dropped: "Cannot read properties of undefined (reading 'dimensions')" on a phone
  // leaving the task page (2026-09-18). The unmount flips one flag and every late callback obeys it.
  assert.match(term, /let disposed = false;/);
  assert.match(term, /return \(\) => \{ disposed = true; window\.removeEventListener\("resize", onResize\)/);
  assert.match(term, /term\.write\(data, \(\) => \{ if \(disposed\) return; pendingWrites -= 1;/);
  assert.match(term, /const lift = \(\) => \{\n\s+if \(disposed\) return;/);
  assert.match(term, /const onResize = \(\) => \{\n\s+if \(disposed\) return;/);
});

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

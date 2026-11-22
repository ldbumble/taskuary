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


// HIDDEN WHILE MOUNTED (the owner, 2026-10-15: Board's Wall, then Chat - Claude's input box was gone)
test("a pane hidden behind another view gives the geometry back, and takes it again on screen", async () => {
  const fs = await import("node:fs");
  const src = fs.readFileSync(new URL("../src/TerminalView.jsx", import.meta.url), "utf8");
  assert.match(src, /if \(!away && !readOnly && geomSeen && ownsGeometry\) \{ send\(\{ type: "release" \}\); ownsGeometry = false; away = true; \}/);
  assert.match(src, /if \(away\) \{ away = false; claim\(\); \}/);
  assert.match(src, /if \(!ownsGeometry && m\.free && !first && !readOnly && ui && onScreen\(\)\) \{ claim\(\); \}/);
});

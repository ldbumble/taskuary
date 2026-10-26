import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// A LINE TYPED WHILE A TASK COMES UP IS HELD, NEVER DROPPED (the owner, 2026-10-26: asked the Assistant while a task was loading on the
// canvas, "it ignored it"). Opening a row holds `busy` for its whole read, and send() returned on `busy` before it drew anything - the
// Enter went nowhere, no line, no word.
const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
const send = view.slice(view.indexOf("const send = async"), view.indexOf("const sendEmoji"));

test("a busy table no longer turns a typed line away", () => {
  assert.doesNotMatch(send, /if \(!t \|\| busy \|\| resetting \|\| turnFlight\.current \|\| pics\.busy\) return;/);
  const guard = send.slice(send.indexOf("if (busy || resetting || turnFlight.current) {"));
  assert.ok(guard.length, "the busy branch is there");
  const branch = guard.slice(0, guard.indexOf("\n    }\n"));
  assert.match(branch, /askLater\.current = \[\.\.\.askLater\.current, t\];/, "the line is held");
  assert.match(branch, /setMsgs\(\(m\) => \[\.\.\.m, \{ id: `u\$\{Date\.now\(\)\}`, role: "user", text: t, shots: \[\], heldAsk: true \}\]\);/,
    "and drawn at once, so it is seen to be heard");
  assert.match(branch, /if \(line == null\) setText\(""\);/, "the box is cleared for the next line");
  // ...not twice: Enter pressed twice in one tick reaches the busy branch with that same line already going
  assert.match(branch, /t === sending\.current \|\| askLater\.current\.includes\(t\)\) return;/);
  // ...and a picture still waits in its tray with the words, as before - nothing about it is dropped either
  assert.match(branch, /if \(resetting \|\| images\.length/);
});

test("the held line goes once the table is free, after an open that was queued, one turn at a time", () => {
  const opens = view.indexOf("if (busy || resetting || !openLater.current) return;");
  const asks = view.indexOf("if (busy || resetting || turnFlight.current || !askLater.current.length) return;");
  assert.ok(opens > 0 && asks > opens, "declared after the open's effect: a queued open takes the turn first");
  const effect = view.slice(asks, view.indexOf("}, [busy, resetting]);", asks));
  assert.match(effect, /const \[t, \.\.\.rest\] = askLater\.current; askLater\.current = rest;\n\s+send\(t, true\);/);
  // sent held, its line is the one already drawn - let go, not drawn a second time
  assert.match(send, /const i = held \? m\.findIndex\(\(x\) => x\.heldAsk && x\.text === t\) : -1;/);
  assert.match(send, /i >= 0 \? m\.map\(\(x, j\) => \(j === i \? \{ \.\.\.x, heldAsk: false \} : x\)\)/);
});

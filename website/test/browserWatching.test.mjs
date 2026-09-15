// Watching the agent's page costs nothing, and typing on it says how. The pane drops every
// keystroke unless the owner has taken over - correct, and silent: the agent wrote "enter your
// User ID in the browser pane" and the keyboard did nothing at all (the owner, 2026-09-14).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");
const pane = src("BrowserPane.jsx");

test("typing on a watched page says how to type on it", () => {
  assert.match(pane, /setAsked\(true\)/);
  assert.match(pane, /Take over to type/);
  assert.match(pane, /asked && !driving/);
});

test("the hint is the door: it takes over itself, it does not just scold", () => {
  const hint = pane.slice(pane.indexOf("asked && !driving"));
  assert.match(hint, /onClick=\{takeOver\}/);
});

test("a hidden tab neither decodes a frame nor acks for the next one", () => {
  assert.match(pane, /document\.hidden/);
  assert.match(pane, /visibilitychange/);
  assert.match(pane, /held\.current/);                 // the frame it stopped on, acked on return
});

test("one session is never watched by two panes at once", () => {
  const term = src("TerminalView.jsx");
  assert.match(term, /\{peek && layout === "chip" && showingBrowser &&/);
});

test("a page that is not moving is still a live page", () => {
  // ack pacing sends no frame at all while the page sits still, so a 4s frame clock read the
  // sign-in form the agent was waiting on as a dead pane (2026-09-15)
  assert.doesNotMatch(pane, /staleTimer/);
  assert.match(pane, /ws\.onclose = \(\) => \{ setLive\(false\)/);
});

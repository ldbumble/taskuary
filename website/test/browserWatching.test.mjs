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

// THE OVERNIGHT WALK, 2026-11-11: the agent handed him the page for a sign-in. The pane's header stood a second, greyed "I'm done" beside
// the step's own, and after his press the chat's pane went with nothing said.
test("a step handed over has one I'm done, and the chat's pane says why it went", () => {
  assert.match(pane, /\{!turn && <Box component="button" onClick=\{\(\) => \(driving \? setDriving\(false\) : takeOver\(\)\)\}/, "the header's press stands aside");
  const term = src("TerminalView.jsx");
  assert.match(term, /useEffect\(\(\) => \{ if \(quiet && showingBrowser\) setLent\(true\); \}, \[quiet, showingBrowser\]\);/);
  // ...never while a step of his still waits there (design round 6, D8: "nothing waits on you there now" stood half a second over the page opening)
  assert.match(term, /const closedLine = !!sid && \(quiet \? lent && !need && !showingBrowser : seen && !browser\.open && !ended\) && \(/);
  assert.match(term, /"Nothing waits on you in the browser now - it comes back here when the agent needs you\."/);
  assert.doesNotMatch(term, /data-tq-browser-closed="" sx=\{\{ \.\.\.mono/);         // his words in the page's own type, never a terminal's
});

// THE BROWSER AUDIT, 2026-11-15: the saved sign-in went in and the site asked a code - the page drew as his with the read taken while the
// sign-in was typed, "Taskuary is signing in ... the picture resumes in a moment" over the code box that was his, until the next poll
test("a page handed to him is read afresh as it is handed, never under a stale 'signing in'", () => {
  const term = src("TerminalView.jsx");
  assert.match(term, /React\.useLayoutEffect\(\(\) => \{ if \(!\(need \|\| yourTurn\)\) return; handed\.current \+= 1; setBrowser\(\(b\) => \(b\.filling \? \{ \.\.\.b, filling: false \} : b\)\); kick\.current\?\.\(\); \}, \[need, yourTurn\]\);/);
});

// ...AND NEVER ON THE READ FROM BEFORE IT (the browser audit, 2026-11-15): for up to 300 ms the view drew the last address and "Take over" -
// the page is shown him once a read made after the hand-over has answered, and one handed over mid-read is read again at once
test("a page handed to him is shown on a read made after the hand-over, never the one before", () => {
  const term = src("TerminalView.jsx");
  assert.match(term, /const ep = handed\.current;/);
  assert.match(term, /setBrowser\(r\.data \|\| \{ open: false \}\); setReadFor\(ep\);/);
  assert.match(term, /setTimeout\(tick, ep !== handed\.current \? 0 :/);
  assert.match(term, /quiet \? need && readFor === handed\.current && showsBrowser\(browser\.open, browser\.url\)/);
});

// THE BROWSER AUDIT, 2026-11-15: in a window ~500 px tall the step's card took 96 of the pane's 215 px and the page under it 119 - below
// SHORT_PANE the card is one line, its full words on hover, so the page he has to work on stays in view
test("a short pane keeps its page: the step's card is one line", () => {
  assert.match(pane, /export const SHORT_PANE = 360;/);
  assert.match(pane, /setShort\(e\.contentRect\.height < SHORT_PANE\)/);
  assert.match(pane, /<TurnBar turn=\{turn\} url=\{url\} onHandBack=\{onHandBack\} short=\{short\} \/>/);
  assert.match(pane, /\{!short && <Box component="span"/);
});

test("a page handed over is his from its first frame: no beat of Take over", () => {
  assert.match(pane, /React\.useLayoutEffect\(\(\) => \{\r?\n    if \(yourTurn && !drivingRef\.current\)/);
});

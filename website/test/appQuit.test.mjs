// QUIT AND A WAITING UPDATE (the owner, 2026-10-25): Quit on the browser's top line - not in the desktop window, which has the tray's -
// with no box asking, the hover saying what stops; the page left behind says it has stopped; Update now with work running says what it
// waits for; and the Assistant's Updates link lights the real button.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { howLine, inDesktop, quitTitle, stoppedLines, updateWaiting, waitingNote } from "../src/appQuit.js";

const src = (f) => fs.readFileSync(path.join(import.meta.dirname, "..", "src", f), "utf8");

test("Quit is for the browser: the desktop window has the tray's", () => {
  assert.equal(inDesktop({ pywebview: {} }), true);
  assert.equal(inDesktop({}), false);
  assert.equal(inDesktop(null), false);
});

test("the hover says what stops with it; the press is the decision", () => {
  assert.equal(quitTitle(""), "Quit Taskuary - stops it here");
  assert.equal(quitTitle("1 running agent"), "Quit Taskuary - stops it here, and the 1 running agent with it");
  const page = src("TaskHubPage.jsx");
  assert.match(page, /<QuitButton onStopped=\{setStopped\} \/>/);
  assert.match(page, /api\.post\("\/api\/quit"/);
  assert.doesNotMatch(page.slice(page.indexOf("function QuitButton"), page.indexOf("export function Stopped")), /confirm\(|alert\(|Dialog/);
});

test("the page left behind says it has stopped, and what stopped with it", () => {
  assert.deepEqual(stoppedLines([])[0], "Taskuary has stopped");
  assert.match(stoppedLines([])[1], /Nothing is lost/);
  assert.match(stoppedLines(["TQ-0012", "TQ-0014"])[1], /^The work on TQ-0012, TQ-0014 stopped with it/);
});

test("while the server still answers, the page says it is shutting down", () => {
  assert.equal(stoppedLines([], false)[0], "Shutting down…");
  assert.match(stoppedLines(["TQ-0012"], false)[1], /^Stopping the work on TQ-0012 and what Taskuary started/);
  const stop = src("TaskHubPage.jsx").slice(src("TaskHubPage.jsx").indexOf("export function Stopped"));
  assert.match(stop, /fetch\("\/api\/health"/, "it asks until the port is closed");
  assert.match(stop, /!inDesktop\(\) && setDown\(true\)/, "the desktop window keeps Shutting down until it closes itself");
});

test("an update that waits says what for", () => {
  assert.equal(updateWaiting({ waiting: true }), true);
  assert.equal(updateWaiting({ queued: true }), true);
  assert.equal(updateWaiting({ restarting: true }), false);
  assert.equal(waitingNote({ waiting: true, waits: "Update waits for 1 running agent" }), "Update waits for 1 running agent - it starts by itself when that is done.");
  assert.equal(waitingNote({ restarting: true }), "");
});


test("the update card says which install this is, and nothing where it has no words for one (the demo read: This is .)", () => {
  for (const how of ["setup", "exe", "pip", "source"]) assert.match(howLine(how), /^This is (the|a) .+\.$/);
  assert.equal(howLine("demo"), ""); assert.equal(howLine(undefined), "");
  assert.match(src("UpdateCard.jsx"), /howLine\(how\)/); assert.doesNotMatch(src("UpdateCard.jsx"), /This is \{/);
});

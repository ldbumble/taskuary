// QUIT AND A WAITING UPDATE (the owner, 2026-10-25): Quit on the browser's top line - not in the desktop window, which has the tray's -
// with no box asking, the hover saying what stops; the page left behind says it has stopped; Update now with work running says what it
// waits for; and the Assistant's Updates link lights the real button.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { inDesktop, quitTitle, stoppedLines, updateWaiting, waitingNote } from "../src/appQuit.js";

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

test("an update that waits says what for", () => {
  assert.equal(updateWaiting({ waiting: true }), true);
  assert.equal(updateWaiting({ queued: true }), true);
  assert.equal(updateWaiting({ restarting: true }), false);
  assert.equal(waitingNote({ waiting: true, waits: "Update waits for 1 running agent" }), "Update waits for 1 running agent - it starts by itself when that is done.");
  assert.equal(waitingNote({ restarting: true }), "");
});

test("the Assistant's #settings=updates&key=update lights the real Update button until it is pressed", () => {
  assert.match(src("SettingsView.jsx"), /<UpdateCard asked=\{only\?\.knob === "update"\} at=\{only\?\.at\} \/>/);
  const card = src("UpdateCard.jsx");
  assert.match(card, /data-tq-knob="update"/);
  assert.match(card, /lit && canApply && !busy \? \{ "data-tq-asked": "" \}/);
  assert.match(card, /const apply = async \(\) => \{\r?\n {4}setLit\(false\);/);
});

// the setup sweep, 2026-10-28: a greyed "Couldn't check" beside Check now said what the warning under it already says
test("a check that did not get through draws no Update button, only Check now and the warning", () => {
  const card = src("UpdateCard.jsx");
  assert.match(card, /\{!\(unknown && !busy\) && <Button size="small" variant="contained"/);
  assert.doesNotMatch(card, /"Couldn't check"/);
});

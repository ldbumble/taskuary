// About your work is one question a screen, filled from the mail, ending on the job description written from it (the owner,
// 2026-10-16: "about your work is too much on one screen. ask one then hit next button ... remove placeholder text").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the questions come one at a time: name, organisation, title, systems, then the job", () => {
  const src = read("FirstRunAbout.jsx");
  assert.match(src, /export const STEPS = \["name", "org", "role", "systems", "job"\];/);
  assert.match(src, /useVerbs\("setup-about", a \? \[/, "its own Back and Next in the row");
  assert.match(src, /&& \(!x\[k\] \|\| \(data\.guessed \|\| \[\]\)\.includes\(k\)\)\)/, "the mail fills only empty boxes and the guessed name");
  assert.doesNotMatch(src, /placeholder=/, "a box is filled from the mail or empty - never a sample answer that reads as one");
});

test("the job is written once the title is answered, and the last press saves what the owner left", () => {
  const src = read("FirstRunAbout.jsx");
  assert.match(src, /if \(step === "role" && who\(a\) !== learnedFor\.current\) learn\(\);/);
  assert.match(src, /api\.post\("\/api\/setup\/first-run\/about\/learn", x\)/);
  assert.match(src, /api\.get\("\/api\/setup\/first-run\/about\/job"\)/);
  assert.match(src, /label: last \? \(busy === "save" \? "Saving…" : job\.state === "ready" \? "Looks right" : "Save"\) : "Next"/);
});

test("a failed email sign-in is the Advisor's line, with what to do", () => {
  assert.match(read("FirstRun.jsx"), /: st\.mail_error \? `\$\{st\.mail_error\} Fix it in the card below and press Connect again/);
});

test("while About your work is on the canvas setup's own Back and Next stand aside, and its question is the Advisor's line", () => {
  const fr = read("FirstRun.jsx");
  assert.match(fr, /view === "about" \? nav\.filter\(\(m\) => m\.id === "finish"\) : nav;/);
  assert.match(fr, /<FirstRunAbout again=\{!!st\.about_done\} onBack=\{\(\) => go\("mail"\)\} onLine=\{setAboutLine\}/);
  assert.match(fr, /about: aiErr \? `\$\{aiErr\} Change AI picks one that does\.` : aboutLine \|\|/);
});

test("the job reads as a document, and Edit opens its text", () => {
  const src = read("FirstRunAbout.jsx");
  assert.match(src, /\{editing \|\| !jobText\.trim\(\)\s*\? <TextField multiline/);
  assert.match(src, /<Md text=\{jobText\} \/>/);
  assert.match(src, /\{editing \? "Done editing" : "Edit"\}/);
});

test("the first time About your work is saved, setup is complete: confetti and one big button into the day", () => {
  const fr = read("FirstRun.jsx"), done = read("SetupDone.jsx");
  assert.match(fr, /const first = !reopened && !st\.about_done; await reload\(\); go\(first \? "done" : "other"\);/);
  assert.match(fr, /\{q === "done" && <SetupDone onDay=\{finishThen\(onFinish\)\} onMore=\{\(\) => go\("other"\)\} \/>\}/);
  assert.match(fr, /const navShown = view === "done" \? \[\] :/);
  assert.match(done, />Setup complete</); assert.match(done, /size="large" onClick=\{onDay\}/); assert.match(done, />Go to my day</);
  assert.match(done, /prefers-reduced-motion: reduce/);
  assert.match(read("setupSteps.js"), /shown === "finish" \? "ready - Go to my day"/);
});

test("an AI connected on the Connections page says so, and the one in use leads the shelf", () => {
  const fr = read("FirstRun.jsx");
  assert.match(fr, /: ai\.connected \? \["on", "Connected - click to make it your AI"\]/);
  assert.match(fr, /\["on", "Your AI - it sorts your mail"\]/);
  assert.match(fr, /const ai = inUse \? \[\.\.\.all\.filter\(\(c\) => c\.title === inUse\)/);
});

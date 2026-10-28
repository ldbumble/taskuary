import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stageOf, mainView, sectionOf } from "../src/stages.js";

// SEND KEEPS CLOSE OUT ON THE PAGE (the owner, 2026-10-27: "I hit send on close out and ... it reopened the task page"). On a real mailbox
// the sent copy comes back marked as Taskuary's own (ReviewSent), so sentElsewhere drops it; with the draft gone nothing was Close out's,
// the stage read "a reply owed, nothing written" and its main view is the task.
const src = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");

test("a reply sent from here is Close out's: the stage stays drafted and Close out stays the page", () => {
  assert.match(src, /const replyHas = !!\(pendingReview \|\| sentReview \|\|/, "the sent reply counts");
  const drafted = stageOf({ focus: "reply", drafted: true }), owed = stageOf({ focus: "reply", drafted: false });
  assert.equal(mainView({ stage: drafted }), "work", "with the sent reply counted, Close out is the page");
  assert.notEqual(mainView({ stage: owed }), "work", "...which is what the page flipped to without it");
  // ...and in the three sections (2026-10-27) both are Close out's section: a reply owed or drafted, sent or not
  assert.equal(sectionOf(drafted), "close");
  assert.equal(sectionOf(owed), "close");
});

test("once open, the main view and its section are held: only a new task, its detail landing, an agent starting or ending, a close or a stack re-reads them", () => {
  assert.match(src, /mainKey = `\$\{selected\}\|\$\{detail\?\.task\?\.TaskId === selected\}\|\$\{!!term\?\.alive\}\|\$\{sessionView\}\|\$\{stacked\}\|\$\{threeUp\}\|\$\{t\?\.Status\}`/);
  assert.match(src, /if \(mainHeld\.current\.key !== mainKey\) mainHeld\.current = \{ key: mainKey, main: mainNow, sec: sectionOf\(taskStage\) \};/);
  assert.match(src, /const main = mainHeld\.current\.main;/);
  // ...a tab's press opens its section for the view it was pressed in, and only that
  assert.match(src, /const section = threeUp \? \(secPick\.key === mainKey \? secPick\.sec : mainHeld\.current\.sec\) : null/);
  assert.match(src, /const openSection = \(s\) => setSecPick\(\{ key: mainKey, sec: s \}\);/);
});

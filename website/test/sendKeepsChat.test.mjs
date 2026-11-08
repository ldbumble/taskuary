import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stageOf, mainView, sectionOf } from "../src/stages.js";

// SEND KEEPS THE PAGE WHERE IT IS (the owner, 2026-10-27: "I hit send ... it reopened the task page"). On a real mailbox the sent copy comes
// back marked as Taskuary's own (ReviewSent), so sentElsewhere drops it; with the draft gone nothing waited on a Send, the stage read "a reply
// owed, nothing written" and its main view was the task. The reply that went still counts - and it went from the chat, which stays the page.
const src = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");

test("a reply sent from here keeps the stage drafted, and the page on the chat", () => {
  assert.match(src, /replyHolds\(\{ pending: !!pendingReview, sent: !!sentReview,/, "the sent reply counts");
  const drafted = stageOf({ focus: "reply", drafted: true }), owed = stageOf({ focus: "reply", drafted: false });
  assert.equal(mainView({ stage: drafted }), "work", "with the sent reply counted, the chat is the page");
  assert.notEqual(mainView({ stage: owed }), "work", "...which is what the page flipped to without it");
  // ...a drafted or sent reply is the chat's; one owed with nothing written opens a plain to-do on Came from (every other kind opens on its chat)
  assert.equal(sectionOf(drafted), "agent");
  assert.equal(sectionOf(owed), "from");
});

test("once open, the main view and its section are held: only a new task, its detail landing, an agent starting or ending, a close or a stack re-reads them", () => {
  // ...and a write-up starting or ending (Stop holds the Agent pane while it writes, 2026-10-29), and a to-do's box starting its agent (`solo`)
  assert.match(src, /mainKey = `\$\{selected\}\|\$\{detail\?\.task\?\.TaskId === selected\}\|\$\{!!term\?\.alive\}\|\$\{sessionView\}\|\$\{stacked\}\|\$\{twoUp\}\|\$\{liveSession \? "live" : t\?\.Status\}\|\$\{!!writingUp\}\|\$\{solo\}`;/);
  assert.match(src, /if \(mainHeld\.current\.key !== mainKey\) mainHeld\.current = \{ key: mainKey, main: mainNow, sec: solo \? "from" : writingUp \? "agent" : homeSection\(t\?\.Kind, taskStage, anyChat\) \};/);
  assert.match(src, /const main = mainHeld\.current\.main;/);
  // ...a tab's press opens its section, and it stays open under the owner: only another task, an agent starting or stopping, a close or
  // reopen or the width fold it - not the detail, the Advisor's pick, the write-up's end or in_progress -> open catching up (2026-11-01)
  assert.match(src, /const pickKey = `\$\{selected\}\|\$\{!!term\?\.alive\}\|\$\{sessionView\}\|\$\{stacked\}\|\$\{twoUp\}\|\$\{\["done", "dropped"\]\.includes\(t\?\.Status\)\}\|\$\{solo\}`;/);
  assert.match(src, /const picked = secPick\.key === pickKey \? secPick\.sec : mainHeld\.current\.sec;/);
  // ...a held section the task no longer lays (the chat, once a to-do is one section again) falls back to the last it has
  assert.match(src, /const section = twoUp \? \(slotKeys\.includes\(picked\) \? picked : slotKeys\.at\(-1\)\) : null/);
  assert.match(src, /const openSection = \(s\) => setSecPick\(\{ key: pickKey, sec: s \}\);/);
  // ...and the Advisor's decision names no section any more: nothing re-keys the page when it lands
  assert.doesNotMatch(src, /advisedHeld|sectionHere|\.section === "close"/);
});

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { madeRow, pressOnto } from "../src/funnelPile.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
// NEW STAYS UP UNTIL WHAT IT MADE IS ON THE TABLE (the owner, 2026-11-09, said twice: "it closed the new ui, then opened the old task up with
// dots on bottom") - now by the one road every press that opens a task takes (AssistantView openTaskCard, 2026-11-17): the task is read whole
// while New stands, then it and its row are drawn in one move, New put down in that same move
test("New's press is held while its task is read, then the task is drawn at once and New goes with it", () => {
  assert.equal(pressOnto({}, [{ key: "task:7", tid: 7 }], { key: "task:12", card: { key: "task:7" } }).below, "task:12");     // the press names a row no rail holds yet
  const view = read("AssistantView.jsx");
  assert.match(view, /return readWhole\(api, req\.tid\)\.then\(/);
  assert.match(view, /if \(made && row !== currentRef\.current && key !== currentRef\.current\?\.key\) ahead\(\);\s+setRailOpen\(false\); if \(old\) setOld\(null\); browseDown\(\);\s+return surface\(key, asUser \|\| null\);/);
});

test("New's button spins until its task is up", () => {
  const sheet = read("NewSheet.jsx");
  // every create that opens its task opens it through the one helper, and an inline card stays busy after it
  assert.equal((sheet.match(/onOpenTask\?\.\(data\.taskId\)/g) || []).length, 0);
  assert.equal((sheet.match(/openIt\(data\.taskId\)/g) || []).length, 3);
  assert.match(sheet, /if \(!\(inline && opened\)\) setBusy\(false\);/);
});

// THE TASK NEW MADE IS ON THE TABLE AT THE PRESS (the owner, 2026-11-16: "on new task it says sent to agent and then the bottom of the screen
// shows ... it should show ... on the agent starting, not randomly on the bottom of the canvas"): New hands the canvas the task as its row, drawn
// as a rail row is, so the "…" of the move that brings its real row waits under the fold, never at the canvas foot under New's card
test("New hands the task it made to the table as its row, drawn at the press", () => {
  assert.deepEqual((({ since, ...r }) => r)(madeRow(12, "Compare three caterers")), { key: "task:12", kind: "task", tid: 12, title: "Compare three caterers" });
  assert.match(read("NewSheet.jsx"), /onOpenTask\?\.\(tid, \{ row: madeRow\(tid, about\) \}\)/);
  assert.match(read("TaskHubPage.jsx"), /row: opts\?\.row \|\| null/);
  const av = read("AssistantView.jsx");
  assert.match(av, /const h = heldTask\(req\.tid\), title = req\.row\?\.title \|\| h\?\.task\?\.Title;/);
  assert.match(av, /\|\| \(made\?\.key === key \? made : null\)/);
  assert.match(av, /if \(made && row !== currentRef\.current && key !== currentRef\.current\?\.key\) ahead\(\);/);
});

// A SEARCHED TASK OPENS AS ITS RAIL ROW DOES (the owner, 2026-11-18: "when you click on searched tasks its so buggy especially when you are on
// another task. it does nothing then moves to new one slowly ... and then the walk highlight disappears"). A task hit pulled `task:N`; the rail
// keys a task's row by its review, its processing or its agent, so nothing drew at the click, the light went out over the task left standing,
// and the task came a round trip later. A task hit is a press of its row by number - the road the Assistant's own opens take.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { pressOnto, rowOfTask } from "../src/funnelPile.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const rail = [{ key: "processing:pi_a", tid: 1, lane: "yours" }, { key: "review:7", tid: 2, lane: "approve" }, { key: "msg:9", tid: 3, lane: "unjudged" }];

test("a task by number is its rail row, whatever key the row wears", () => {
  assert.equal(rowOfTask(rail, 2)?.key, "review:7");
  assert.equal(rowOfTask(rail, "1")?.key, "processing:pi_a");
  assert.equal(rowOfTask(rail, 3), null);            // an unjudged row is no row to stand on
  assert.equal(rowOfTask(rail, 4), null);            // a closed task is on no row: its link opens it
  assert.equal(rowOfTask(null, 1), null);
  // ...so the press draws that row at once (pressOnto names it), where `task:2` named no row on the rail
  const card = rail[0], walk = { on: card.key };
  assert.equal(pressOnto(walk, rail, { key: rowOfTask(rail, 2).key, card }).below, "review:7");
  assert.ok(!rail.some((r) => r.key === pressOnto(walk, rail, { key: "task:2", card }).below));
});

test("a search hit on a task goes the rail row's road, not a pull of task:N", () => {
  const feed = read("FeedView.jsx"), view = read("AssistantView.jsx");
  assert.match(feed, /onOpenTask=\{\(tid, h\) => \{ searchPicked\(\); return onPress \? onPress\(tid, h\) : onOpenTask\?\.\(tid\); \}\}/);
  assert.doesNotMatch(feed, /onPull\(\{ TaskId: tid/);
  assert.match(view, /<FeedView [\s\S]*?onPress=\{pressRow\}/);
  // ...AND A TASK ON NO ROW THE SAME ROAD (2026-11-19: a closed task searched while on another went by its link - a hash round trip, the task
  // left standing lit until the read came): its row made at the press, as New's is (madeRow), pulled with it so it draws at once
  assert.match(view, /const pressRow = \(n, hit = null\) => \{\n\s*prefetchTask\(api, n\);\n\s*const row = rowOfTask\(pile\?\.items, n\);\n\s*if \(row\) railPress\(row\.key\); else openTaskCard\(\{ tid: n, row: hit \? madeRow\(n, hit\.title\) : null \}\);/);
  assert.doesNotMatch(view, /openAppLink\(`task=\$\{n\}`\)/);
  assert.doesNotMatch(view, /`task:\$\{r\.TaskId\}`/);   // keyForRow's task-hit key: no road takes it now
});

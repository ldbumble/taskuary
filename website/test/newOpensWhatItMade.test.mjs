import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { holdsNew, pressOnto } from "../src/funnelPile.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
// a task open on the table, then New posted over it: the New card is the live page
const msgs = [{ id: "a1", role: "assistant", card: { key: "task:7", tid: 7 } }, { id: "b2", role: "browse", area: "new", state: { kind: "agent" } }];
const rail = [{ key: "task:7", tid: 7, title: "Held mail from a stranger" }];

test("New's press opening the task it just made keeps the card up: no rail row holds that task yet, so nothing draws at the press", () => {
  assert.equal(pressOnto({}, rail, { key: "task:12", card: { key: "task:7" } }).below, "task:12");     // the press names it...
  assert.equal(rail.find((i) => i.key === "task:12"), undefined);                                      // ...but no row draws it
  assert.equal(holdsNew(msgs, "b2", rail, "task:12"), true);
});

test("the card goes with the press as ever when the row draws at once, the page is not New, or nothing is browsed", () => {
  assert.equal(holdsNew(msgs, "b2", [...rail, { key: "task:12" }], "task:12"), false);                 // its row is drawn ahead
  assert.equal(holdsNew(msgs, "b2", [...rail, { key: "task:12", settling: true }], "task:12"), true);  // a settling row draws nothing
  assert.equal(holdsNew([...msgs.slice(0, 1), { id: "b3", role: "browse", area: "reports" }], "b3", rail, "task:12"), false);
  assert.equal(holdsNew(msgs, null, rail, "task:12"), false);
  assert.equal(holdsNew(msgs, "b2", rail, null), false);
});

test("the pull puts New down when the task lands, and New's button spins until then", () => {
  const view = read("AssistantView.jsx"), sheet = read("NewSheet.jsx");
  assert.match(view, /const held = holdsNew\(msgsRef\.current, browsingRef\.current, pileRef\.current\?\.items, key\);/);
  assert.match(view, /if \(!held\) browseDown\(\);\s+const going = surface\(key, asUser \|\| null\);\s+if \(held\) Promise\.resolve\(going\)\.finally\(\(\) => browseDownRef\.current\?\.\(\)\);/);
  // every create that opens its task opens it through the one helper, and an inline card stays busy after it
  assert.equal((sheet.match(/onOpenTask\?\.\(data\.taskId\)/g) || []).length, 0);
  assert.equal((sheet.match(/openIt\(data\.taskId\)/g) || []).length, 3);
  assert.match(sheet, /if \(!\(inline && opened\)\) setBusy\(false\);/);
});

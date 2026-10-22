import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// RESTART IS ONE PRESS FROM THE ERROR (the owner, 2026-10-22): "the WhatsApp bridge is not running ... - Restart bridge starts it"
// is read on the connector card, in the bell and on the walk's card, and each puts the button beside the sentence.
const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const helper = read("waBridge.js"), card = read("ConnectorsView.jsx"), bell = read("TaskHubPage.jsx"), walk = read("gameItem.jsx");

test("the error that names Restart bridge is what brings the button, and it calls the card's own restart verb", () => {
  const re = new RegExp(helper.match(/namesRestart = \(text\) => \/(.+?)\/\.test/)[1]);
  assert.ok(re.test("the WhatsApp bridge is not running at http://127.0.0.1:8977 - Restart bridge starts it"));
  assert.ok(re.test("the WhatsApp bridge would not stay up after 6 starts in a row - Taskuary stopped starting it; Restart bridge tries again"));
  assert.ok(!re.test("the WhatsApp bridge is not running at http://wa-box.example:8977 - start it where it runs"), "an external bridge has no button");
  assert.match(helper, /api\.post\(`\/api\/connectors\/\$\{cid\}\/wa\/bridge\/restart`\)/);
});

test("the connector card puts it under the saved error and under a failed Test", () => {
  assert.match(card, /const BridgeRestart = \(\{ cid, text \}\) => \{[\s\S]+?if \(!cid \|\| !namesRestart\(text\)\) return null;[\s\S]+?restartBridge\(cid\)/);
  assert.match(card, /\{!test\.ok && <BridgeRestart cid=\{cid\} text=\{test\.detail\} \/>\}/);
  assert.match(card, /<TestLine test=\{test\} mt=\{1\} cid=\{conn\.ConnectorId\} \/>/);
  assert.match(card, /✗ \{conn\.LastErrorPlain \|\| conn\.LastError\}<\/Typography>\s*<BridgeRestart cid=\{conn\.ConnectorId\} text=\{conn\.LastError\} \/>/);
});

test("the bell and the walk's connection card carry it for a bridge this machine runs", () => {
  assert.match(bell, /\{p\.restart && p\.connector && <Button[^>]*data-tq-restart-bridge=""[\s\S]+?onClick=\{\(\) => restart\(p\)\}>/);
  assert.match(bell, /try \{ await restartBridge\(p\.connector\); \}/);
  assert.match(walk, /\{item\.restart && <Btn kind="gold"[^>]*onClick=\{\(\) => play\(null, null, \(\) => restartBridge\(String\(item\.key\)\.split\(":"\)\[1\]\)\)\}>↻ Restart bridge<\/Btn>\}/);
});

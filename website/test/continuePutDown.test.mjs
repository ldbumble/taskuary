// CONTINUE AS IS (press audit B23b, 2026-10-01): "Continuing" showed at 299 ms but the row stayed under ON YOU until the
// next pile refresh at 2110 ms. The rail moves the row to Agents working AT THE PRESS now - the put-down pattern Mark done
// uses (ac051beb) - held until the server's pile has it working, and put back if the continue fails.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { asPressed, levelOf } from "../src/funnelPile.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const rows = [
  { key: "processing:a", tid: 19, lane: "saved", order_band: 2, surfaced: true, kind: "agent" },
  { key: "processing:b", tid: 4, lane: "yours", order_band: 2 },
  { key: "processing:c", tid: null, mid: 7, lane: "fyi", order_band: 4 },
];

test("asPressed draws a continued task under Agents working and drops one being put down - and nothing else", () => {
  assert.equal(asPressed(rows, {}), rows, "nothing pressed: the server's rows as they are");
  const cont = asPressed(rows, { continuing: 19 });
  assert.equal(levelOf(cont[0]), "agents");
  assert.equal(levelOf(rows[0]), "later", "the server's row is not touched");
  assert.deepEqual(cont.slice(1), rows.slice(1));
  const left = asPressed(rows, { leaving: 4 });
  assert.deepEqual(left.map((i) => i.key), ["processing:a", "processing:c"], "a row with no task is never dropped with it");
});

test("the walk's Continue moves the row at the press, holds it until the pile agrees, and puts it back on failure", () => {
  const box = read("ContinueBox.jsx");
  const go = box.slice(box.indexOf("const go = async"), box.indexOf("const body ="));
  assert.ok(go.indexOf("onPress?.()") > -1 && go.indexOf("onPress?.()") < go.indexOf("api.post"), "at the press, before the request");
  assert.match(go, /catch \(e\) \{[^}]*onFail\?\.\(msg\)/, "a continue that fails puts it back");
  const view = read("AssistantView.jsx");
  assert.match(view, /onPress=\{\(\) => setContinuingTid\(continueOn\.task\.TaskId\)\}/);
  assert.match(view, /onFail=\{\(\) => setContinuingTid\(null\)\}/);
  assert.match(view, /asPressed\(pile\.items, \{ leaving: leavingTid, continuing: continuingTid \}\)/);
  assert.match(view, /attentionBand\(row\) === 5\)\) setContinuingTid\(null\)/, "held until the server's pile has it working");
});

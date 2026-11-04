// CONTINUE AS IS (press audit B23b, 2026-10-01): "Continuing" showed at 299 ms but the row stayed as it was until the
// next pile refresh at 2110 ms. The rail draws the row working AT THE PRESS now - the put-down pattern Mark done
// uses (ac051beb) - held until the server's pile has it working, and put back if the continue fails. Since 2026-10-21 it stays
// where it is, under Tasks, its icon ringed: a task does not change section when its agent starts.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { answersTo, asPressed, levelOf, putDownLanded, rowKeys, sameKey } from "../src/funnelPile.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const rows = [
  { key: "processing:a", tid: 19, lane: "saved", order_band: 2, surfaced: true, put_down: true, kind: "agent" },
  { key: "processing:b", tid: 4, lane: "yours", order_band: 2 },
  { key: "processing:c", tid: null, mid: 7, lane: "fyi", order_band: 4 },
];

test("asPressed draws a continued task working, in Tasks, and drops one being put down - and nothing else", () => {
  assert.equal(asPressed(rows, {}), rows, "nothing pressed: the server's rows as they are");
  const cont = asPressed(rows, { continuing: 19 });
  assert.equal(cont[0].lane, "working"); assert.equal(levelOf(cont[0]), "task");
  assert.equal(rows[0].lane, "saved", "the server's row is not touched");
  assert.deepEqual(cont.slice(1), rows.slice(1));
  const left = asPressed(rows, { leaving: 4 });
  assert.deepEqual(left.map((i) => i.key), ["processing:a", "processing:c"], "a row with no task is never dropped with it");
  // ...and the rows a walk press reads (rule 4) leave by key, the rest as they are
  assert.deepEqual(asPressed(rows, { read: ["fyis:processing:a", "processing:a"] }).map((i) => i.key), rows.slice(1).map((i) => i.key));
  assert.equal(asPressed(rows, { read: [] }), rows);
});

test("the walk's Continue moves the row at the press, holds it until the pile agrees, and puts it back on failure", () => {
  const box = read("ContinueBox.jsx");
  const go = box.slice(box.indexOf("const go = async"), box.indexOf("const body ="));
  assert.ok(go.indexOf("onPress?.()") > -1 && go.indexOf("onPress?.()") < go.indexOf("api.post"), "at the press, before the request");
  assert.match(go, /catch \(e\) \{[^}]*onFail\?\.\(msg\)/, "a continue that fails puts it back");
  const view = read("AssistantView.jsx");
  assert.match(view, /onPress=\{\(\) => setContinuingTid\(continueOn\.task\.TaskId\)\}/);
  assert.match(view, /onFail=\{\(\) => setContinuingTid\(null\)\}/);
  assert.match(view, /asPressed\(pile\.items, \{ leaving: leavingTid, continuing: continuingTid, read: readGone\?\.keys \}\)/);
  assert.match(view, /row\.lane === "working"\)\) setContinuingTid\(null\)/, "held until the server's pile has it working");
});

// REMIND ME HID THE ROW UNTIL A RELOAD (UX walk, 2026-10-22): the put-down was held until the row left the pile, but a reminded
// task stays in it, For later - so the rail went on dropping it. The hold ends when the row is gone OR put away.
test("a put-down lands when its row leaves the pile or comes back For later, and not before", () => {
  assert.equal(putDownLanded(rows, 4), false, "still an ordinary row: the server has not answered yet");
  assert.equal(putDownLanded(rows, 99), true, "closed: gone from the pile");
  assert.equal(putDownLanded([{ ...rows[1], deferred: true, back_at: "2026-10-23 09:00:00" }], 4), true, "reminded: For later");
  assert.match(read("AssistantView.jsx"), /putDownLanded\(pile\.items, leavingTid, leavingWas\.current\)\) setLeavingTid\(null\)/);
});

// MARK DONE ON A WATCHED ROW (the owner, 2026-11-04): the row was under Watching when pressed, so the pile it was pressed on read as landed and
// the rail drew it again until the server's answer came. Put away counts only when the press put it there.
test("a row put away before the press has landed only when it leaves the pile, or the press puts it away another way", () => {
  const watched = { ...rows[1], watching: true }, reminded = { ...rows[1], deferred: true };
  assert.equal(putDownLanded([watched], 4, watched), false, "Mark done on a watched row: still on the pile, not landed");
  assert.equal(putDownLanded([], 4, watched), true, "gone from the pile: landed");
  assert.equal(putDownLanded([watched], 4, rows[1]), true, "Watch it: the press put it under Watching");
  assert.equal(putDownLanded([reminded], 4, watched), true, "Remind me on a watched row: For later");
  assert.equal(putDownLanded([reminded], 4, reminded), false, "Mark done on a reminded row: still For later, not landed");
});

// A REPORT THAT RE-RAN ON THE TABLE (the owner, 2026-11-02): its row has a new key and answers to the old one the card still holds. A press
// takes off every row the keys name by key or alias - the ring's own matching - and the walk's row and the one put down are one row
test("a press reads a re-run row by key or alias, and sameKey sees one row", () => {
  const rr = [{ key: "processing:new", aliases: ["processing:old"] }, { key: "processing:other" }];
  assert.ok(answersTo(rr[0], "processing:old") && !answersTo(rr[1], "processing:old"));
  assert.ok(sameKey(rr, "processing:old", "processing:new") && !sameKey(rr, "processing:old", "processing:other"));
  assert.ok(sameKey([], "processing:old", "processing:new", { key: "processing:new", aliases: ["processing:old"] }), "the card's own aliases join them");
  assert.deepEqual(rowKeys(rr, ["processing:old"]).sort(), ["processing:new", "processing:old"]);
  assert.deepEqual(asPressed(rr, { read: ["processing:old"] }).map((r) => r.key), ["processing:other"]);
});

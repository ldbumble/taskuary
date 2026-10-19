// ONE RECORD OF WHAT IS ON THE TABLE (general fix 4, 2026-10-18): folded or under a page, the item keeps its key and the Advisor
// keeps quiet; "Thinking..." only while a judgement is in flight; a Board-opened task hears its Advisor line.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { adviceRead, sameTarget, tableOf } from "../src/tableState.js";
import { adviceKeyFor } from "../src/advice.js";

const src = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("folded by its X or under a page, the item stays on the table and the Advisor keeps quiet", () => {
  assert.deepEqual(tableOf({ current: "task:7" }), { key: "task:7", folded: false, place: false, speaks: true });
  assert.deepEqual(tableOf({ current: "task:7", foldedKey: "task:7" }), { key: "task:7", folded: true, place: false, speaks: false });
  assert.equal(tableOf({ cardKey: "task:9", browsing: "b123" }).speaks, false, "a page opened over it: no strip, no button acting on it");
  assert.equal(tableOf({ current: "task:7", setup: true }).speaks, false);
  assert.equal(tableOf({}).key, null);
});

test("Thinking shows only while the server says a judgement is in flight", () => {
  assert.deepEqual(adviceRead({ pending: true }, "task:7"), { advice: null, asking: "task:7" });
  // EVERY REASON IS KEPT (2026-10-19): dropped, the strip went blank under the row; each is said as a sentence (words.json)
  for (const why of ["quiet", "working", "no_actions", "nothing", "off"])
    assert.deepEqual(adviceRead({ none: why }, "task:7"), { advice: { none: why, for: "task:7" }, asking: null }, why);
  assert.equal(adviceRead({ verb: "reply", line: "Erin asked." }, "task:7").advice.for, "task:7");
  assert.equal(adviceRead({ none: "no_ai" }, "task:7").advice.none, "no_ai");
  assert.equal(adviceRead({ none: "cap" }, "task:7").advice.none, "cap");
  assert.deepEqual(adviceRead({}, "task:7"), { advice: null, asking: null }, "an old server's bare {} is no spinner");
});

test("a task opened by name hears the Advisor's event, which names it by the rail's key", () => {
  const ev = { key: "processing:abc", target_kind: "task", target_id: 12 };
  assert.ok(sameTarget(ev, { key: "task:12" }));
  assert.equal(adviceKeyFor(ev, { key: "task:12" }), "task:12");
  assert.equal(adviceKeyFor(ev, { key: "task:13" }), null);
  assert.equal(adviceKeyFor({ key: "msg:4", target_kind: "message", target_id: 4 }, { key: "task:4" }), null, "a message is not task 4");
  assert.equal(adviceKeyFor(ev, { key: "review:3", tid: 12 }), "review:3", "the walk's item knows its task too");
});

test("the page wires the record: the strip, the box's subject, the folded line and the ring", () => {
  assert.match(src, /const table = tableOf\(/);
  assert.match(src, /const shownAdvice = table\.speaks \?/);
  assert.match(src, /if \(card\) openCardRef\.current = null;/, "a task put on the table ends the page the chat was answering about");
  assert.match(src, /live && foldedNow \? \{ role: "button"/, "the folded item on the table is its own door back");
  assert.match(src, /onCurrent=\{\(\) => \{ setRailOpen\(false\); if \(table\.folded \|\| table\.place\)/, "the ringed rail row reopens it");
  assert.match(src, /firstRun && browsing \?/, "a sidebar place opens during setup, with the way back");
  assert.doesNotMatch(src, /setTimeout\(\(\) => \{ if \(n === adviceAsk\.current\) setAsking\(null\); \}, 20000\)/, "no 20 s spinner that then shows nothing");
});

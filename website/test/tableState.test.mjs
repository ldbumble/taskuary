// ONE RECORD OF WHAT IS ON THE TABLE (general fix 4, 2026-10-18): folded or under a page, the item keeps its key and the Advisor
// keeps quiet; "Thinking..." only while a judgement is in flight; a Board-opened task hears its Advisor line.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { adviceRead, sameTarget, tableOf, tableWords } from "../src/tableState.js";
import { adviceKeyFor } from "../src/advice.js";

const src = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("folded by its X or under a page, the item stays on the table and the Advisor keeps quiet", () => {
  assert.deepEqual(tableOf({ current: "task:7" }), { key: "task:7", folded: false, place: false, speaks: true });
  assert.deepEqual(tableOf({ current: "task:7", foldedKey: "task:7" }), { key: "task:7", folded: true, place: false, speaks: false });
  assert.equal(tableOf({ cardKey: "task:9", browsing: "b123" }).speaks, false, "a page opened over it: no strip, no button acting on it");
  assert.equal(tableOf({ current: "task:7", setup: true }).speaks, false);
  // ...but a task opened over setup is in view, and its Advisor speaks (2026-10-26); folded or under a page it still keeps quiet
  assert.equal(tableOf({ cardKey: "task:7", setup: true, over: true }).speaks, true);
  assert.equal(tableOf({ cardKey: "task:7", setup: true, over: true, browsing: "b1" }).speaks, false);
  assert.equal(tableOf({ cardKey: "task:7", foldedKey: "task:7", setup: true, over: true }).speaks, false);
  assert.match(src, /tableOf\(\{ current, cardKey, foldedKey, browsing, setup: setupOn\.current, over: !!setupCard \}\)/, "the page says what is over setup");
  assert.equal(tableOf({}).key, null);
});

// G5 (2026-10-19 UI walk): Connections opened over TQ-0003 and the rail still said "on the table", the box "Ask about this one"
test("a page over the item: the rail's tag and the box say it is under the page, not in view", () => {
  const under = tableWords(tableOf({ current: "task:3", browsing: "b1" }), "TQ-0003");
  assert.equal(under.tag, "under this page");
  assert.match(under.box, /^Ask about this page or TQ-0003/);
  assert.equal(under.phone, "Ask about this page…");
  const shown = tableWords(tableOf({ current: "task:3" }), "TQ-0003");
  assert.equal(shown.tag, "on the table");
  assert.match(shown.box, /^Ask about this one/);
  // ...the open box over a task, and a phone's: "Talk to Taskuary…" (the owner, 2026-10-28), the resting pill still "Ask…"
  assert.equal(shown.phone, "Talk to Taskuary…");
  assert.equal(shown.name, "Tell Taskuary what to do with TQ-0003", "the pill names the task its words do not");
  assert.equal(under.name, "Ask Taskuary about this page or TQ-0003");
  assert.match(tableWords(tableOf({ cardKey: "task:9" })).box, /^Ask about this one/, "a task opened by name is on the table too");
  assert.match(tableWords(tableOf({ browsing: "b1" })).box, /^Ask Taskuary anything/, "a page with nothing under it");
  assert.match(src, /tag=\{tableSays\.tag\}/, "the rail draws the tag tableWords chose");
  // ...and the box its words - but the one-row bar's pill, at rest and widened, its own short ones (2026-10-26)
  // ...and the pill at rest with no task on the table the short hint, the long one ran on under its send button (2026-10-26)
  // ...and the pill at rest the SAME "Ask…" whatever is on the table (the owner, 2026-10-27: "always the same size and words")
  assert.match(src, /placeholder=\{boxNarrow && !boxWide \? "Ask…" : phone \|\| \(boxIsOver && boxWide\) \? tableSays\.phone : !popOn \? tableSays\.box : boxWide \? "[^"]+" : "Ask…"\}/, "and the box its words");
  assert.match(src, /aria-label=\{tableSays\.name\}/, "and its name the task on the table");
});

// NO "THINKING..." (the owner, 2026-10-23): the server answers at once with the Advisor's one decision - a lit verb, silent or with its
// fact - and the page keeps every answer it reads for the key it asked about
test("the Advisor's decision is read whole, silent or not, and nothing is ever a spinner", () => {
  assert.deepEqual(adviceRead({ pending: true }, "task:7"), { advice: null }, "an old server's pending is no spinner");
  assert.equal(adviceRead({ verb: "reply", line: "" }, "task:7").advice.verb, "reply", "an obvious move: lit, said by nothing");
  assert.equal(adviceRead({ verb: "chase", line: "Ray Colton: 4 days, no answer." }, "task:7").advice.for, "task:7");
  assert.equal(adviceRead({ verb: null, state: "agent_asking", line: "" }, "task:7").advice.state, "agent_asking", "nothing lit is an answer too");
  for (const why of ["no_ai", "off", "nothing"]) assert.equal(adviceRead({ none: why }, "task:7").advice.none, why, why);
  assert.deepEqual(adviceRead({}, "task:7"), { advice: null });
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
  assert.match(src, /const shownAdvice = table\.speaks && !litNow \?/);
  assert.match(src, /if \(card\) openCardRef\.current = null;/, "a task put on the table ends the page the chat was answering about");
  assert.match(src, /live && foldedNow \? \{ role: "button"/, "the folded item on the table is its own door back");
  assert.match(src, /onCurrent=\{\(\) => \{ setRailOpen\(false\); if \(table\.folded \|\| table\.place\) unfoldTable\(\)/, "the ringed rail row reopens it");
  // folded by its X it is put away (UX walk, 2026-10-22): no "on the table" ring, no #task - and its plain row opens it again in place
  assert.match(src, /current=\{old \|\| table\.folded \|\|/, "a folded task's row is not marked on the table");
  assert.match(src, /litTable\.tid && !table\.folded \? `#task=/, "nor does the address name it");
  assert.match(src, /if \(isCur \|\| \(table\.folded && key === table\.key\)\) \{ setRailOpen\(false\); if \(table\.folded \|\| table\.place\) unfoldTable\(\); return; \}\n\s*pull\(key, null\);/, "its row unfolds it, not a second pull");
  assert.match(src, /firstRun && \(browsing \|\| setupCard\) && <div data-tq-setup-over=""/, "a sidebar place - or a task - opens during setup, with the way back");
  assert.doesNotMatch(src, /setTimeout\(\(\) => \{ if \(n === adviceAsk\.current\) setAsking\(null\); \}, 20000\)/, "no 20 s spinner that then shows nothing");
});

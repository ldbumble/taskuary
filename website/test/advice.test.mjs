// The pure piece of the Advisor's line (website/src/advice.js): which live event is about the item on the table.
// A real function under test, not a source regex.
import test from "node:test";
import assert from "node:assert/strict";
import { adviceKeyFor, stripWord } from "../src/advice.js";

// C2 (the UI audit, 2026-10-21): the strip's word and the lit button are one decision (advice.stripWord)
test("a working agent's strip says it is working and lights Next, even with no AI connected", () => {
  const w = stripWord({ speaks: true, aiOff: true, key: "task:9", lane: "working" });
  assert.equal(w.noAi, false); assert.equal(w.none.none, "working"); assert.equal(w.pick.none, "working");
  const n = stripWord({ speaks: true, advice: { none: "no_ai", for: "task:9" }, key: "task:9", lane: "working" });
  assert.equal(n.none.none, "working", "a no-AI answer read for a working agent is said as working");
  const p = stripWord({ speaks: true, aiOff: true, key: "task:3", lane: "asked" });
  assert.equal(p.noAi, true); assert.equal(p.pick.none, "no_ai", "elsewhere the strip asks for an AI, and the row lights nothing of its own");
  const s = { verb: "reply", line: "x" };
  assert.equal(stripWord({ speaks: true, shown: s, key: "k", lane: "asked" }).pick, s, "a line lights its verb");
});

test("an advice event is about the item on the table when it names its key or one of its aliases", () => {
  const cur = { key: "processing:pi_1", aliases: ["msg:3", "agent:1", "task:1"] };
  assert.equal(adviceKeyFor({ key: "task:1" }, cur), "processing:pi_1");          // the event carries the legacy key, the table the rail's
  assert.equal(adviceKeyFor({ key: "processing:pi_1" }, cur), "processing:pi_1");
  assert.equal(adviceKeyFor({ key: "task:2" }, cur), null);
  assert.equal(adviceKeyFor({ key: "task:1" }, "task:1"), "task:1");               // a bare key still works
  assert.equal(adviceKeyFor({ key: "task:1" }, null), null);
  assert.equal(adviceKeyFor({}, cur), null);
});

// WHEN THE STRIP SPEAKS (the owner, 2026-10-13: "not while waiting or walking through things"): only the line read for the
// item on the table now, only at rest, and never over an agent at work.
test("the strip speaks only for the item on the table, at rest, and never over an agent at work", async () => {
  const { adviceShown } = await import("../src/advice.js");
  const a = { verb: "continue", line: "You usually continue it.", for: "processing:7" };
  const item = { key: "processing:7", lane: "blocked" };
  assert.equal(adviceShown(a, item, false), a);
  assert.equal(adviceShown(a, { key: "processing:8", lane: "blocked" }, false), null, "the last item's line over the next one");
  assert.equal(adviceShown(a, item, true), null, "an act in flight");
  assert.equal(adviceShown(a, { ...item, lane: "working" }, false), null, "an agent continued and at work");
  assert.equal(adviceShown({ ...a, for: undefined }, item, false), null, "a line nobody read for this table");
  assert.equal(adviceShown(a, null, false), null);
  assert.equal(adviceShown({ ...a, line: "" }, item, false), null);
});

test("the page draws the gated line, starts each item with none, and drops a read the table outran", async () => {
  const fs = await import("node:fs"), path = await import("node:path");
  const src = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
  assert.match(src, /<AdvisorNext advice=\{shownAdvice\} onPropose=\{pressAdvice\} \/>/);
  assert.match(src, /try \{ return await proposeDirect\(a\.verb, key, true, a\.revision\); \}/);
  assert.match(src, /advised=\{stripPick \|\| setupLit\}/);
  assert.doesNotMatch(src, /<AdvisorNext advice=\{advice\}/);
  assert.match(src, /if \(!keep\) setAdvice\(null\)/);
  assert.match(src, /if \(n !== adviceAsk\.current\) return;[\s\S]{0,400}?setAdvice\(got\);/);
  // the read is for the key ON THE TABLE - the walk's item or a task opened by name - and shown only for it
  assert.match(src, /useEffect\(\(\) => \{ readAdvice\(onTable\); setChanged\(null\); \}, \[onTable, readAdvice\]\);/);
  assert.match(src, /table\.speaks && !litNow \? adviceShown\(advice, \{ key: table\.key, lane: currentItem\?\.lane \}, busy\) : null/);
  // ...and while it is out, a quiet line - no button - says the advice is coming
  assert.match(src, /data-tq-advice-thinking=""><div className="tq-next-txt">Thinking about this one…<\/div>/);
  assert.doesNotMatch(src, /picks up where it left off, and comes back here/, "the continue receipt is gone");
});

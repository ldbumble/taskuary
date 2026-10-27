// The pure piece of the Advisor's line (website/src/advice.js): which live event is about the item on the table.
// A real function under test, not a source regex.
import test from "node:test";
import assert from "node:assert/strict";
import { adviceKeyFor, nothingToAdd, stripWord } from "../src/advice.js";

// C2 (the UI audit, 2026-10-21): the strip's word and the lit button are one decision (advice.stripWord)
test("a working agent lights Next and says nothing, even with no AI connected", () => {
  const w = stripWord({ speaks: true, aiOff: true, key: "task:9", lane: "working" });
  assert.equal(w.noAi, false); assert.deepEqual(w.pick, { verb: "next", line: "", for: "task:9" });
  const n = stripWord({ speaks: true, advice: { none: "no_ai", for: "task:9" }, key: "task:9", lane: "working" });
  assert.equal(n.pick.verb, "next", "a no-AI answer read for a working agent is Next");
  // ...no AI is said only where the move needs one (advisor.decide's needs_ai) - a rule decides the rest with none connected
  const ask = { verb: "reply", line: "", needs_ai: true, for: "task:3" };
  const p = stripWord({ speaks: true, aiOff: true, shown: ask, advice: ask, key: "task:3", lane: "asked" });
  assert.equal(p.noAi, true); assert.equal(p.pick.none, "no_ai", "the strip asks for an AI, and its own Connect is the lit move");
  const rule = { verb: "continue", line: "", needs_ai: false, for: "task:4" };
  assert.equal(stripWord({ speaks: true, aiOff: true, shown: rule, advice: rule, key: "task:4", lane: "stopped" }).pick, rule, "the rule's own move needs no AI");
  const s = { verb: "reply", line: "x" };
  assert.equal(stripWord({ speaks: true, shown: s, key: "k", lane: "asked" }).pick, s, "a decision lights its verb");
  assert.deepEqual(stripWord({ speaks: true, advice: { none: "off", for: "k" }, key: "k", lane: "asked" }).pick, { verb: "next", line: "", for: "k" }, "any other none: Next, silent");
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

// WHEN THE STRIP SPEAKS (the owner, 2026-10-13: "not while waiting or walking through things"): only the decision read for the
// item on the table now, only at rest; an agent at work is Next; and the OBVIOUS move is silent - lit, said by nothing (2026-10-23)
test("the strip speaks only for the item on the table, at rest, and an agent at work is Next", async () => {
  const { adviceShown } = await import("../src/advice.js");
  const a = { verb: "continue", line: "You usually continue it.", for: "processing:7" };
  const item = { key: "processing:7", lane: "blocked" };
  assert.equal(adviceShown(a, item, false), a);
  assert.equal(adviceShown(a, { key: "processing:8", lane: "blocked" }, false), null, "the last item's line over the next one");
  assert.equal(adviceShown(a, item, true), null, "an act in flight");
  assert.deepEqual(adviceShown(a, { ...item, lane: "working" }, false), { ...a, verb: "next", line: "", state: "working" }, "an agent continued and at work");
  assert.equal(adviceShown({ ...a, for: undefined }, item, false), null, "a line nobody read for this table");
  assert.equal(adviceShown(a, null, false), null);
  assert.deepEqual(adviceShown({ ...a, line: "" }, item, false), { ...a, line: "" }, "a silent decision still lights its button");
  assert.equal(adviceShown({ ...a, verb: null }, item, false), null, "a decision that lights nothing (an agent asking) is not shown");
});

test("the page draws the gated line, starts each item with none, and drops a read the table outran", async () => {
  const fs = await import("node:fs"), path = await import("node:path");
  const src = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
  assert.match(src, /<AdvisorNext advice=\{shownAdvice\} onPropose=\{pressAdvice\} onErr=\{setErr\} \/>/);
  // ...and a move the server runs at once (Not ours) runs at once from the Advisor's copy too - never a proposal card with Cancel
  // ...and every press runs where it is proposed (the 2026-10-25 sweep): proposeDirect runs it, so no caller runs it a second time
  assert.match(src, /try \{ return await proposeDirect\(a\.verb, key, true, a\.revision\); \}/);
  assert.match(src, /if \(c\.revision\) await pressAdvice\(\{ verb, key, revision: c\.revision \}\); else await proposeDirect\(verb, key, true, null\);/, "a stamped chip's move is not run twice");
  assert.match(src, /if \(data\.auto\) \{ await runProposal\(data\); return \{ \.\.\.data, ran: true \}; \}/, "a press draws no proposal card with Cancel while it runs");
  assert.match(src, /advised=\{stripPick \|\| setupLit\}/);
  assert.doesNotMatch(src, /<AdvisorNext advice=\{advice\}/);
  assert.match(src, /if \(!keep\) setAdvice\(null\)/);
  assert.match(src, /if \(n !== adviceAsk\.current\) return;[\s\S]{0,400}?setAdvice\(got\);/);
  // the read is for the key ON THE TABLE - the walk's item or a task opened by name - and shown only for it
  assert.match(src, /useEffect\(\(\) => \{ readAdvice\(onTable\); setChanged\(null\); \}, \[onTable, readAdvice\]\);/);
  assert.match(src, /table\.speaks && !litNow \? adviceShown\(advice, \{ key: table\.key, lane: currentItem\?\.lane \}, busy\) : null/);
  // ...and while it is out, nothing: no "Thinking..." (the owner, 2026-10-23) - the rule's button is lit at once
  assert.doesNotMatch(src, /data-tq-advice-thinking|Thinking about this one/);
  assert.doesNotMatch(src, /picks up where it left off, and comes back here/, "the continue receipt is gone");
});

// the menu's Advisor notes with nothing to add (the overnight walk, 2026-10-26): "Copy is the lit button." - never the app's word "lit"
test("nothing to add names the button in plain words", () => {
  assert.equal(nothingToAdd({ label: "Copy", verb: "copy" }), "Nothing to add - Copy is the next move.");
  assert.equal(nothingToAdd({ label: "Next", verb: "next" }), "Nothing to add on this one.");
  assert.equal(nothingToAdd({}), "Nothing to add on this one.");
  assert.doesNotMatch(nothingToAdd({ label: "Send", verb: "approve" }), /\blit\b/i);
});
